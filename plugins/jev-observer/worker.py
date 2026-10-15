"""Background Jev observation: drain a conversation's pending rows in order, off the turn thread.

Bounded retries (``MAX_ATTEMPTS`` calls per row, counted across restarts); every final failure
is an explicit ``error`` row with the key redacted. Nothing here raises into the chat.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from . import store

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (2, 8)

# Both serve TypeSafe's Jev 1.13 with the same request body; TypeSafe's own API wins when its key is
# set. Keys come from the API Keys settings page (.env), read through the profile's secret scope.
PROVIDERS = (
    {"name": "typesafe", "key": "TYPESAFE_API_KEY", "endpoint": "https://api.typesafe.ai/v1/systemone",
     "model": "jev-1.13.0"},
    {"name": "defapi", "key": "DEFAPI_API_KEY", "endpoint": "https://api.defapi.org/api/v1/decisions",
     "model": "typesafe/jev-1.13"},
)

_locks: dict[tuple[str, str], threading.Lock] = {}
_locks_guard = threading.Lock()


def _observe(reply: str, turn_id: str, provider: dict[str, str], api_key: str) -> dict[str, Any]:
    """Seam for tests: the vendored Jev client with the chosen provider's endpoint, model and key."""
    from .jev_defapi import observe
    return observe(reply, turn_id=turn_id, api_key=api_key, endpoint=provider["endpoint"], model=provider["model"])


def _resolve() -> tuple[Optional[dict[str, str]], Optional[str]]:
    """First provider whose key is configured, with that key; ``(None, None)`` when neither is."""
    from agent.secret_scope import get_secret
    for provider in PROVIDERS:
        if key := get_secret(provider["key"]):
            return provider, key
    return None, None


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _redact(text: str, key: Optional[str]) -> str:
    if key:
        text = text.replace(key, "[redacted]")
    return text[:500]


def _session_lock(session_id: str) -> threading.Lock:
    from hermes_constants import hermes_home_key
    k = (hermes_home_key(), session_id)
    with _locks_guard:
        return _locks.setdefault(k, threading.Lock())


def _observe_row(row) -> None:
    provider, key = _resolve()
    if provider is None:
        store.finish_error(row["id"], "no Jev key: add a TypeSafe or DefAPI key in Settings > Providers")
        return
    last_error = ""
    attempts = row["attempts"]
    while attempts < MAX_ATTEMPTS:
        if attempts:
            _sleep(BACKOFF_SECONDS[min(attempts - 1, len(BACKOFF_SECONDS) - 1)])
        attempts = store.bump_attempts(row["id"])
        if attempts is None:  # lease lost to another process; it finishes the row
            return
        try:
            obs = _observe(row["assistant_reply"], row["turn_id"], provider, key)
        except Exception as exc:  # health: allow BLE001 -- network, HTTP and validation failures all become the row's error record
            last_error = _redact(f"{type(exc).__name__}: {exc}", key)
            logger.debug("jev-observer attempt %d for row %s failed: %s", attempts, row["id"], last_error)
            continue
        # Outside the retry: a DB failure here must not buy a second paid observation.
        store.finish_ok(row, dict(obs["states"]), f'{provider["name"]}:{provider["model"]}')
        return
    store.finish_error(row["id"], last_error or "retry budget exhausted")


def drain(session_id: str) -> None:
    """Observe every pending row of one conversation, oldest first, so deltas see earlier results."""
    try:
        with _session_lock(session_id):
            while (row := store.claim_next(session_id)) is not None:
                _observe_row(row)
    except Exception:
        logger.warning("jev-observer worker failed for session %s", session_id, exc_info=True)


def requeue_all() -> None:
    """Resume rows a previous process left pending (crash, exit mid-request)."""
    try:
        for session_id in store.pending_sessions():
            drain(session_id)
    except Exception:
        logger.warning("jev-observer requeue failed", exc_info=True)


def spawn(target, *args) -> threading.Thread:
    from agent.memory_provider import spawn_context_thread
    thread = spawn_context_thread(target, name="jev-observer", args=args)
    thread.start()
    return thread
