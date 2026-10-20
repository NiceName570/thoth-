"""jev-observer: passive Jev observation of completed Thoth exchanges.

``post_llm_call`` captures the user message and final reply into a local ``pending`` row and hands
Jev scoring to a background thread. The hook returns nothing and touches no prompt, reply or
memory, so observations cannot influence the conversation. With the ``contextual`` setting on
(default), each exchange is also judged in context as ``jev-context-v1`` (see ``rubric.py``). Opt in from the desktop Plugins page
(or ``hermes plugins enable jev-observer``); the Jev key goes in Settings > Providers.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from . import context_store, lifecycle, settings, store, worker

logger = logging.getLogger(__name__)

_requeued_homes: set[str] = set()
_requeue_guard = threading.Lock()


def _requeue_once() -> None:
    from hermes_constants import hermes_home_key
    key = hermes_home_key()
    with _requeue_guard:
        if key in _requeued_homes:
            return
        _requeued_homes.add(key)
    worker.spawn(worker.requeue_all)


def _on_post_llm_call(*, session_id: str = "", turn_id: str = "", user_message: Any = None,
                      assistant_response: Any = None, conversation_history: Any = None,
                      model: str = "", platform: str = "", **_: Any) -> None:
    try:
        if not lifecycle.is_enabled():
            return
        reply = store._text(assistant_response)
        if not session_id or not turn_id or not reply.strip():
            return
        _requeue_once()
        row_id = store.insert_pending(
            session_id=session_id, turn_id=turn_id, user_message=store._text(user_message), assistant_reply=reply,
            platform=platform or "", chat_model=model or "",
            history=conversation_history if isinstance(conversation_history, list) else [])
        if row_id is None:
            return
    except Exception:
        logger.warning("jev-observer capture failed; chat continues", exc_info=True)
        return
    # Separate so a contextual failure can never keep the baseline row from being scored.
    try:
        if settings.current()["contextual"]:
            context_store.insert_pending(row_id, session_id)
    except Exception:
        logger.warning("jev-observer contextual capture failed; baseline continues", exc_info=True)
    try:
        worker.spawn(worker.drain, session_id)
    except Exception:
        logger.warning("jev-observer could not start its worker; chat continues", exc_info=True)


def register(ctx) -> None:
    from .cli import handle, setup
    ctx.register_hook("post_llm_call", _on_post_llm_call)
    ctx.register_cli_command("jev-observer", "Export or check passive Jev observations", setup, handle)
