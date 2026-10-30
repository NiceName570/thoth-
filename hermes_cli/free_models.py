"""Free daily models: which providers give some models away, which models those are, and whether
an account has paid credits.

Thoth lists these providers first on the Providers page, marks their free models in the model
picker, narrows a provider with no credits to its free models, and rotates through free models
when one runs out (``agent/route_chain.py``). The lists come from each provider's public model
catalog, cached on disk for a day: a picker open refreshes a stale list in the background, and a
process-wide timer refreshes it once a day.
"""

from __future__ import annotations

import contextvars
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
# A refresh that reached no provider at all (offline, first launch) is retried this soon instead.
_RETRY_SECONDS = 15 * 60
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
        data = json.loads((path or _cache_path()).read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cache(data: dict, path: Optional[Path] = None) -> None:
    path = path or _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
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


def _ordered(levels: dict[str, Optional[str]]) -> dict[str, Optional[str]]:
    """Free models with their top reasoning level, auto-routers last."""
    return ({m: v for m, v in levels.items() if m not in _ROUTER_IDS}
            | {m: v for m, v in levels.items() if m in _ROUTER_IDS})


def _top_level(efforts: object) -> Optional[str]:
    from agent.reasoning_effort import EFFORT_LADDER
    if not isinstance(efforts, list):
        return None
    known = [e for e in (str(x).strip().lower() for x in efforts) if e in EFFORT_LADDER and e != "none"]
    return max(known, key=EFFORT_LADDER.index) if known else None


def _openrouter_level(item: dict) -> Optional[str]:
    """``off`` when the model can't reason, its top published level when it lists them, else
    ``reasoning``; None when the catalog doesn't say."""
    from hermes_cli.models_reasoning_caps import parse_openrouter_reasoning_capabilities
    caps = parse_openrouter_reasoning_capabilities(item)
    if caps is None:
        return None
    if not caps["supports_reasoning"]:
        return "off"
    return _top_level(caps.get("supported_efforts")) or "reasoning"


def _zen_level(item: dict) -> Optional[str]:
    capabilities = item.get("capabilities")
    reasoning = capabilities.get("reasoning") if isinstance(capabilities, dict) else None
    if not isinstance(reasoning, dict) or "supported" not in reasoning:
        return None
    if not reasoning.get("supported"):
        return "off"
    return _top_level(reasoning.get("effort")) or "reasoning"


def _zero_priced(pricing: object) -> bool:
    if not isinstance(pricing, dict):
        return False
    try:
        return float(pricing.get("prompt", "x")) == 0 and float(pricing.get("completion", "x")) == 0
    except (TypeError, ValueError):
        return False


def _openrouter_free() -> dict[str, Optional[str]]:
    items = _items(_get_json("https://openrouter.ai/api/v1/models"))
    return _ordered({str(i["id"]): _openrouter_level(i) for i in items
                     if (str(i["id"]).endswith(":free") or _zero_priced(i.get("pricing")))
                     and _is_chat_model(str(i["id"]), i)})


def _kilocode_free() -> dict[str, Optional[str]]:
    from hermes_cli.models_pricing import _kilo_pricing_scope
    base = _kilo_pricing_scope()
    if not base:
        return {}
    items = _items(_get_json(base + "/models"))
    return _ordered({str(i["id"]): _openrouter_level(i) for i in items
                     if i.get("isFree") and _is_chat_model(str(i["id"]), i)})


def _cline_free() -> dict[str, Optional[str]]:
    """Cline's catalog lists ids only; levels are borrowed from OpenRouter's (``free_model_levels``)."""
    base = (_env("CLINE_BASE_URL") or "https://api.cline.bot/api/v1").rstrip("/")
    items = _items(_get_json(base + "/models"))
    return _ordered({str(i["id"]): None for i in items
                     if str(i["id"]).endswith(":free") and _is_chat_model(str(i["id"]), i)})


def _opencode_zen_free() -> dict[str, Optional[str]]:
    base = (_env("OPENCODE_ZEN_BASE_URL") or "https://opencode.ai/zen/v1").rstrip("/")
    items = _items(_get_json(base + "/models"))
    return _ordered({str(i["id"]): _zen_level(i) for i in items
                     if str(i["id"]).endswith("-free") and _is_chat_model(str(i["id"]))})


def _nous_free() -> dict[str, Optional[str]]:
    """Nous Portal's free models need a signed-in account to list; none without one."""
    from hermes_cli.models_pricing import get_pricing_for_provider
    try:
        pricing = get_pricing_for_provider("nous") or {}
    except Exception:
        return {}
    return _ordered({mid: None for mid, entry in pricing.items() if _zero_priced(entry)})


# Each returns ``{free model id: top reasoning level or None}`` in catalog order.
_FETCHERS: dict[str, Callable[[], dict[str, Optional[str]]]] = {
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
    levels = dict(cache.get("levels") or {})
    reached = False
    for slug in providers:
        try:
            fresh = _FETCHERS[slug]()
        except Exception:
            logger.debug("Free-model refresh failed for %s", slug, exc_info=True)
            fresh = {}
        if fresh:
            lists[slug] = list(fresh)
            levels[slug] = {m: level for m, level in fresh.items() if level}
            reached = True
    now = time.time()
    _write_cache({"fetched_at": now if reached else now - REFRESH_SECONDS + _RETRY_SECONDS,
                  "providers": lists, "levels": levels}, path)
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

    # The caller's context carries its profile scope, so keys and base URLs come from that profile.
    ctx = contextvars.copy_context()
    threading.Thread(target=ctx.run, args=(_run,), name="free-models-refresh", daemon=True).start()


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


def free_model_levels() -> dict[str, dict[str, str]]:
    """``{provider: {free model id: top reasoning level}}`` from the cached lists: a level from
    ``EFFORT_LADDER``, ``reasoning`` (reasons, levels unpublished) or ``off``. A model whose own
    catalog gives no level borrows OpenRouter's entry for the same id (Cline and Kilo Code use
    OpenRouter's ids); unknown models are left out."""
    cache = _read_cache()
    lists, stored = cache.get("providers") or {}, cache.get("levels") or {}
    openrouter = stored.get("openrouter") or {}

    def level(own: Optional[str], model: str) -> Optional[str]:
        return own if own not in (None, "reasoning") else openrouter.get(model) or own
    levels = {}
    for slug in FREE_MODEL_PROVIDERS:
        own = stored.get(slug) or {}
        known = {m: level(own.get(m), m) for m in lists.get(slug) or []}
        if known := {m: level for m, level in known.items() if level}:
            levels[slug] = known
    return levels


# Lower runs first: the strongest published reasoning level, then reasoning models that publish
# no levels (and models no catalog describes), then low-only, then models that don't reason.
_LEVEL_RANK = {"ultra": 0, "max": 0, "xhigh": 0, "high": 1, "medium": 2, "reasoning": 3,
               "low": 4, "minimal": 4, "off": 5}


def by_reasoning(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """*pairs* of (provider, free model) with the strongest reasoners first; ties keep their order,
    and auto-routers stay last."""
    levels = free_model_levels()

    def rank(pair: tuple[str, str]) -> tuple[bool, int]:
        provider, model = pair
        return model in _ROUTER_IDS, _LEVEL_RANK.get((levels.get(provider) or {}).get(model, "reasoning"), 3)
    return sorted(pairs, key=rank)


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

    # Bound to the profile that started it; other profiles refresh when their picker opens on a
    # list older than a day.
    path = _cache_path()

    def _loop() -> None:
        while True:
            time.sleep(REFRESH_SECONDS)
            try:
                refresh_free_models(path=path)
            except Exception:
                logger.debug("Daily free-model refresh failed", exc_info=True)

    ctx = contextvars.copy_context()
    threading.Thread(target=ctx.run, args=(_loop,), name="free-models-daily", daemon=True).start()


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
    ctx = contextvars.copy_context()
    threading.Thread(target=ctx.run, args=(_read,), name=f"credits-{slug}", daemon=True).start()
    return cached[1] if cached else CREDITS_UNKNOWN


# ─── Free mode ──────────────────────────────────────────────────────────

def free_mode_enabled() -> bool:
    """``model.free_mode``: use only free models (off by default)."""
    from hermes_cli.config import load_config
    model = (load_config() or {}).get("model")
    return isinstance(model, dict) and model.get("free_mode") is True


def first_free_model() -> Optional[tuple[str, str]]:
    """The strongest reasoner among the signed-in providers' free models (``by_reasoning``); ties
    go to the first provider in list order."""
    from hermes_cli.models_detect import provider_has_credentials
    lists = free_models_by_provider()
    if not any(lists.values()):
        lists = free_models_by_provider(blocking=True)
    pairs = by_reasoning([(slug, m) for slug in FREE_MODEL_PROVIDERS
                          if lists.get(slug) and provider_has_credentials(slug) for m in lists[slug]])
    if pairs:
        return pairs[0]
    return None


# ─── Model picker ───────────────────────────────────────────────────────

NO_CREDITS_WARNING = "No credits on this account, so only its free models are listed."
_FREE_PRICE = {"input": "free", "output": "free", "cache": None, "free": True}


def decorate_picker_rows(rows: list[dict]) -> None:
    """In place, for each provider with free daily models: list its free models (marked free), and
    when the account reports no credits, list only those. A provider that can't report credits
    keeps every model, with the free ones marked. Free mode lists only free models, so every other
    provider row, local and custom endpoints included, drops out."""
    lists = free_models_by_provider()
    free_mode = free_mode_enabled()
    if free_mode:
        rows[:] = [row for row in rows if lists.get(str(row.get("slug") or "").strip().lower())]
    for row in rows:
        slug = str(row.get("slug") or "").strip().lower()
        free = lists.get(slug) or []
        if not free or not isinstance(row.get("models"), list):
            continue
        models = [m for m in row["models"] if isinstance(m, str)]
        pricing = row.get("pricing") if isinstance(row.get("pricing"), dict) else {}
        for mid in free:
            pricing[mid] = {**(pricing.get(mid) or {}), **_FREE_PRICE}
        if free_mode or credit_state(slug) == CREDITS_NONE:
            row["models"] = [m for m in models if m in free] + [m for m in free if m not in models]
            if not free_mode:
                row["warning"] = row.get("warning") or NO_CREDITS_WARNING
        else:
            row["models"] = models + [m for m in free if m not in models]
        if isinstance(row.get("total_models"), int):
            row["total_models"] = len(row["models"])
        row["pricing"] = pricing
        # Featured models are what the picker shows before the user curates it: free ones included.
        featured = row.get("featured_models") if isinstance(row.get("featured_models"), list) else []
        row["featured_models"] = free if free_mode else featured + [m for m in free if m not in featured]
