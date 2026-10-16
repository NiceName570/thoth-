"""Free daily models: which providers give some models away, which models those are, and whether
an account has paid credits.

Thoth lists these providers first on the Providers page, marks their free models in the model
picker, narrows a provider with no credits to its free models, and rotates through free models
when one runs out (``agent/free_rotation.py``). The lists come from each provider's public model
catalog, cached on disk for a day: a picker open refreshes a stale list in the background, and a
process-wide timer refreshes it once a day.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Providers with free daily models, in the order Thoth lists them and rotates through them.
FREE_MODEL_PROVIDERS: tuple[str, ...] = ("cline", "nous", "openrouter", "kilocode", "opencode-zen")

REFRESH_SECONDS = 24 * 60 * 60
_CREDITS_TTL_SECONDS = 60 * 60
_TIMEOUT = 8.0

# Catalog rows that are not chat models (safety classifiers, music, embeddings) never rotate in.
_NOT_CHAT_MARKERS = ("content-safety", "guard", "embed", "lyria", "moderation", "rerank", "tts", "whisper")
# Auto-routers over free models work but pick the model themselves, so they go last.
_ROUTER_IDS = frozenset({"openrouter/free", "kilo-auto/free"})

_lock = threading.Lock()
_refreshing: set[str] = set()
_credits_cache: dict[tuple[str, str], tuple[float, str]] = {}
_timer_started = False


def _cache_path() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home()) / "cache" / "free_models.json"


def _read_cache(path: Optional[Path] = None) -> dict:
    try:
        data = json.loads((path or _cache_path()).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cache(data: dict, path: Optional[Path] = None) -> None:
    path = path or _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        logger.debug("Could not write the free-model cache", exc_info=True)


def _env(key: str) -> str:
    from hermes_cli.config import get_env_value
    return (get_env_value(key) or "").strip()


def _get_json(url: str, headers: Optional[dict] = None) -> Optional[dict]:
    from hermes_cli.models import _HERMES_USER_AGENT
    from hermes_cli.models_pricing import _get_json as get_json
    return get_json(url, {"Accept": "application/json", "User-Agent": _HERMES_USER_AGENT, **(headers or {})}, _TIMEOUT)


def _items(payload: Optional[dict]) -> list[dict]:
    data = payload.get("data") if isinstance(payload, dict) else None
    return [item for item in data if isinstance(item, dict) and item.get("id")] if isinstance(data, list) else []


def _is_chat_model(model_id: str, item: Optional[dict] = None) -> bool:
    lowered = model_id.lower()
    if any(marker in lowered for marker in _NOT_CHAT_MARKERS):
        return False
    architecture = (item or {}).get("architecture")
    outputs = architecture.get("output_modalities") if isinstance(architecture, dict) else None
    return not isinstance(outputs, list) or "text" in outputs


def _ordered(ids: list[str]) -> list[str]:
    unique = list(dict.fromkeys(ids))
    return [m for m in unique if m not in _ROUTER_IDS] + [m for m in unique if m in _ROUTER_IDS]


def _zero_priced(pricing: object) -> bool:
    if not isinstance(pricing, dict):
        return False
    try:
        return float(pricing.get("prompt", "x")) == 0 and float(pricing.get("completion", "x")) == 0
    except (TypeError, ValueError):
        return False


def _openrouter_free() -> list[str]:
    items = _items(_get_json("https://openrouter.ai/api/v1/models"))
    return _ordered([str(i["id"]) for i in items
                     if (str(i["id"]).endswith(":free") or _zero_priced(i.get("pricing")))
                     and _is_chat_model(str(i["id"]), i)])


def _kilocode_free() -> list[str]:
    from hermes_cli.models_pricing import _kilo_pricing_scope
    base = _kilo_pricing_scope()
    if not base:
        return []
    items = _items(_get_json(base + "/models"))
    return _ordered([str(i["id"]) for i in items if i.get("isFree") and _is_chat_model(str(i["id"]), i)])


def _cline_free() -> list[str]:
    base = (_env("CLINE_BASE_URL") or "https://api.cline.bot/api/v1").rstrip("/")
    items = _items(_get_json(base + "/models"))
    return _ordered([str(i["id"]) for i in items if str(i["id"]).endswith(":free") and _is_chat_model(str(i["id"]), i)])


def _opencode_zen_free() -> list[str]:
    base = (_env("OPENCODE_ZEN_BASE_URL") or "https://opencode.ai/zen/v1").rstrip("/")
    items = _items(_get_json(base + "/models"))
    return _ordered([str(i["id"]) for i in items if str(i["id"]).endswith("-free") and _is_chat_model(str(i["id"]))])


def _nous_free() -> list[str]:
    """Nous Portal's free models need a signed-in account to list; none without one."""
    from hermes_cli.models_pricing import get_pricing_for_provider
    try:
        pricing = get_pricing_for_provider("nous") or {}
    except Exception:
        return []
    return _ordered([mid for mid, entry in pricing.items() if _zero_priced(entry)])


_FETCHERS: dict[str, Callable[[], list[str]]] = {
    "cline": _cline_free,
    "nous": _nous_free,
    "openrouter": _openrouter_free,
    "kilocode": _kilocode_free,
    "opencode-zen": _opencode_zen_free,
}


def refresh_free_models(providers: tuple[str, ...] = FREE_MODEL_PROVIDERS,
                        path: Optional[Path] = None) -> dict[str, list[str]]:
    """Re-read every provider's free models and save them to *path* (default: this profile's cache).
    A provider whose catalog can't be read keeps its last list rather than losing its free models
    to one failed request."""
    cache = _read_cache(path)
    lists = dict(cache.get("providers") or {})
    for slug in providers:
        try:
            fresh = _FETCHERS[slug]()
        except Exception:
            logger.debug("Free-model refresh failed for %s", slug, exc_info=True)
            fresh = []
        if fresh:
            lists[slug] = fresh
    _write_cache({"fetched_at": time.time(), "providers": lists}, path)
    return lists


def _refresh_in_background() -> None:
    # The cache path is bound here, in the caller's profile scope, not inside the thread.
    path = _cache_path()
    with _lock:
        if str(path) in _refreshing:
            return
        _refreshing.add(str(path))

    def _run() -> None:
        try:
            refresh_free_models(path=path)
        finally:
            with _lock:
                _refreshing.discard(str(path))

    threading.Thread(target=_run, name="free-models-refresh", daemon=True).start()


def free_models_by_provider(*, blocking: bool = False) -> dict[str, list[str]]:
    """``{provider: [free model ids]}`` in rotation order. A list older than a day is refreshed: in
    the background by default (the picker never waits on it), inline when ``blocking``."""
    ensure_daily_refresh()
    cache = _read_cache()
    stale = time.time() - float(cache.get("fetched_at") or 0) >= REFRESH_SECONDS
    if stale and blocking:
        return refresh_free_models()
    if stale:
        _refresh_in_background()
    lists = cache.get("providers") or {}
    return {slug: list(lists.get(slug) or []) for slug in FREE_MODEL_PROVIDERS}


def free_models(provider: str, *, blocking: bool = False) -> list[str]:
    return free_models_by_provider(blocking=blocking).get((provider or "").strip().lower(), [])


def is_free_model(provider: str, model: str) -> bool:
    return bool(model) and model in free_models(provider)


def ensure_daily_refresh() -> None:
    """Start the once-a-day refresh timer for this process (idempotent)."""
    global _timer_started
    with _lock:
        if _timer_started:
            return
        _timer_started = True

    def _loop() -> None:
        while True:
            time.sleep(REFRESH_SECONDS)
            try:
                refresh_free_models()
            except Exception:
                logger.debug("Daily free-model refresh failed", exc_info=True)

    threading.Thread(target=_loop, name="free-models-daily", daemon=True).start()


# ─── Credits ────────────────────────────────────────────────────────────

CREDITS_NONE, CREDITS_AVAILABLE, CREDITS_UNKNOWN = "none", "available", "unknown"


def _openrouter_credits(key: str) -> str:
    auth = {"Authorization": f"Bearer {key}"}
    credits = (_get_json("https://openrouter.ai/api/v1/credits", auth) or {}).get("data")
    if isinstance(credits, dict) and "total_credits" in credits:
        try:
            remaining = float(credits.get("total_credits") or 0) - float(credits.get("total_usage") or 0)
        except (TypeError, ValueError):
            remaining = None
        if remaining is not None:
            return CREDITS_AVAILABLE if remaining > 0 else CREDITS_NONE
    info = (_get_json("https://openrouter.ai/api/v1/key", auth) or {}).get("data")
    if not isinstance(info, dict):
        return CREDITS_UNKNOWN
    if info.get("is_free_tier") is True:
        return CREDITS_NONE
    remaining = info.get("limit_remaining")
    if isinstance(remaining, (int, float)) and remaining <= 0:
        return CREDITS_NONE
    return CREDITS_AVAILABLE


def _kilocode_credits(key: str) -> str:
    from hermes_cli.models_pricing import _kilo_pricing_scope
    base = _kilo_pricing_scope()
    root = base.split("/api/", 1)[0] if "/api/" in base else base
    balance = (_get_json(root + "/api/profile/balance", {"Authorization": f"Bearer {key}"}) or {}).get("balance")
    if not isinstance(balance, (int, float)) or isinstance(balance, bool):
        return CREDITS_UNKNOWN
    return CREDITS_AVAILABLE if balance > 0 else CREDITS_NONE


_CREDIT_READERS: dict[str, tuple[str, Callable[[str], str]]] = {
    "openrouter": ("OPENROUTER_API_KEY", _openrouter_credits),
    "kilocode": ("KILOCODE_API_KEY", _kilocode_credits),
}


def credit_state(provider: str, *, blocking: bool = False) -> str:
    """Whether *provider*'s account has paid credits: ``none``, ``available`` or ``unknown`` (the
    provider can't report it, or no key). Cached for an hour per key; a cold read answers
    ``unknown`` and fills the cache in the background unless ``blocking``."""
    slug = (provider or "").strip().lower()
    reader = _CREDIT_READERS.get(slug)
    key = _env(reader[0]) if reader else ""
    if not reader or not key:
        return CREDITS_UNKNOWN
    cache_key = (slug, key[-8:])
    cached = _credits_cache.get(cache_key)
    if cached and time.time() - cached[0] < _CREDITS_TTL_SECONDS:
        return cached[1]

    def _read() -> str:
        try:
            state = reader[1](key)
        except Exception:
            state = CREDITS_UNKNOWN
        _credits_cache[cache_key] = (time.time(), state)
        return state

    if blocking:
        return _read()
    threading.Thread(target=_read, name=f"credits-{slug}", daemon=True).start()
    return cached[1] if cached else CREDITS_UNKNOWN


# ─── Model picker ───────────────────────────────────────────────────────

NO_CREDITS_WARNING = "No credits on this account, so only its free models are listed."
_FREE_PRICE = {"input": "free", "output": "free", "cache": None, "free": True}


def decorate_picker_rows(rows: list[dict]) -> None:
    """In place, for each provider with free daily models: list its free models (marked free), and
    when the account reports no credits, list only those. A provider that can't report credits
    keeps every model, with the free ones marked."""
    lists = free_models_by_provider()
    for row in rows:
        slug = str(row.get("slug") or "").strip().lower()
        free = lists.get(slug) or []
        if not free or not isinstance(row.get("models"), list):
            continue
        models = [m for m in row["models"] if isinstance(m, str)]
        pricing = row.get("pricing") if isinstance(row.get("pricing"), dict) else {}
        for mid in free:
            pricing[mid] = {**(pricing.get(mid) or {}), **_FREE_PRICE}
        if credit_state(slug) == CREDITS_NONE:
            row["models"] = [m for m in models if m in free] + [m for m in free if m not in models]
            row["warning"] = row.get("warning") or NO_CREDITS_WARNING
        else:
            row["models"] = models + [m for m in free if m not in models]
        if isinstance(row.get("total_models"), int):
            row["total_models"] = len(row["models"])
        row["pricing"] = pricing
