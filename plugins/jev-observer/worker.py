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
KEY_NAME = "DEFAPI_API_KEY"

_locks: dict[tuple[str, str], threading.Lock] = {}
_locks_guard = threading.Lock()


def _observe(reply: str, turn_id: str, api_key: str) -> dict[str, Any]:
    """Seam for tests: the vendored DefAPI client, unchanged apart from the injected key."""
    from .jev_defapi import observe
    return observe(reply, turn_id=turn_id, api_key=api_key)


def _api_key() -> Optional[str]:
    from agent.secret_scope import get_secret
    return get_secret(KEY_NAME)


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
    key = _api_key()
    if not key:
        store.finish_error(row["id"], f"{KEY_NAME} is not configured")
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
            obs = _observe(row["assistant_reply"], row["turn_id"], key)
        except Exception as exc:  # health: allow BLE001 -- network, HTTP and validation failures all become the row's error record
            last_error = _redact(f"{type(exc).__name__}: {exc}", key)
            logger.debug("jev-observer attempt %d for row %s failed: %s", attempts, row["id"], last_error)
            continue
        # Outside the retry: a DB failure here must not buy a second paid observation.
        store.finish_ok(row, dict(obs["states"]))
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
