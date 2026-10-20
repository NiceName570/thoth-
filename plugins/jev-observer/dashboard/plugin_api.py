"""Read-only view of what jev-observer has observed.

Mounted at ``/api/plugins/jev-observer/``. This adds no behaviour to the
observer: every endpoint reads the same rows that ``hermes jev-observer
timeline|export`` prints, so the Settings page can answer two questions
without opening a terminal — "is it running?" and "what did the context
window actually carry?".

Nothing here writes, and nothing here is ever injected into a conversation.

The plugin package directory is not importable by name (``jev-observer`` has a
hyphen), so the modules are loaded through a synthetic package shell — the same
shape ``plugins/plugin_loader`` builds for the plugin itself.
"""

from __future__ import annotations

import importlib
import sys
import threading
import types
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

_PLUGIN_DIR = Path(__file__).resolve().parents[1]
_REL_PKG = "jev_obs_dashboard_readonly"

router = APIRouter()

_BOUNDS = {"context_window": (0, 12), "open_corrections": (0, 6)}



def _pkg_shell() -> str:
    """A package shell whose ``__path__`` is the plugin dir, so ``from . import`` works."""
    if _REL_PKG not in sys.modules:
        pkg = types.ModuleType(_REL_PKG)
        pkg.__path__ = [str(_PLUGIN_DIR)]  # type: ignore[attr-defined]
        sys.modules[_REL_PKG] = pkg
    return _REL_PKG


def _mod(name: str):
    return importlib.import_module(f"{_pkg_shell()}.{name}")


def _status_counts(conn, table: str) -> dict[str, int]:
    try:
        return {str(row[0]): int(row[1]) for row in conn.execute(f"SELECT status, COUNT(*) FROM {table} GROUP BY status")}
    except Exception:
        return {}


@router.get("/summary")
def summary() -> dict[str, Any]:
    """Counts, recency and configuration — the "is it working" panel."""
    store = _mod("store")
    settings = _mod("settings")
    conn = store.connect()
    try:
        observations = _status_counts(conn, "observations")
        contextual = _status_counts(conn, "context_observations")
        last_ok = conn.execute("SELECT MAX(observed_at) FROM observations WHERE status='ok'").fetchone()[0]
        last_capture = conn.execute("SELECT MAX(created_at) FROM observations").fetchone()[0]
        last_error = conn.execute(
            "SELECT error, observed_at FROM observations WHERE status='error' ORDER BY id DESC LIMIT 1").fetchone()
        last_context_error = conn.execute(
            "SELECT error, observed_at FROM context_observations WHERE status='error' ORDER BY id DESC LIMIT 1").fetchone()
        recent = [
            {"session_id": row[0], "observations": int(row[1]), "last": row[2]}
            for row in conn.execute(
                "SELECT session_id, COUNT(*), MAX(created_at) FROM observations "
                "GROUP BY session_id ORDER BY MAX(id) DESC LIMIT 8")
        ]
    finally:
        conn.close()

    provider = None
    try:  # the same key resolution the worker uses; never let a missing key 500 this page
        provider = (_mod("worker")._resolve() or (None, None))[0]
        provider = (provider or {}).get("name") if isinstance(provider, dict) else None
    except Exception:
        provider = None

    return {
        "observer_version": store.OBSERVER_VERSION,
        "observations": observations,
        "contextual": contextual,
        "last_capture": last_capture,
        "last_ok": last_ok,
        "last_error": dict(last_error) if last_error else None,
        "last_context_error": dict(last_context_error) if last_context_error else None,
        "provider": provider,
        "settings": settings.current(),
        "recent_sessions": recent,
    }


@router.get("/sessions")
def sessions(limit: int = Query(30, ge=1, le=200)) -> dict[str, Any]:
    """Conversations that have observations, newest first."""
    store = _mod("store")
    conn = store.connect()
    try:
        rows = conn.execute(
            "SELECT o.session_id, COUNT(*), SUM(o.status='ok'), SUM(o.status='pending'), SUM(o.status='error'), "
            "MAX(o.created_at) FROM observations o GROUP BY o.session_id ORDER BY MAX(o.id) DESC LIMIT ?",
            (limit,)).fetchall()
        out = []
        for r in rows:
            try:
                ctx_total = conn.execute(
                    "SELECT COUNT(*) FROM context_observations WHERE session_id=?", (r[0],)).fetchone()[0]
            except Exception:
                ctx_total = 0
            out.append({"session_id": r[0], "observations": int(r[1]), "ok": int(r[2] or 0),
                        "pending": int(r[3] or 0), "errors": int(r[4] or 0), "last": r[5],
                        "contextual": int(ctx_total)})
    finally:
        conn.close()
    return {"sessions": out}


@router.get("/timeline")
def timeline(session: str = Query(..., min_length=1), run: Optional[str] = None) -> dict[str, Any]:
    """Per-turn contextual judgments plus the window each one carried."""
    context_report = _mod("context_report")
    try:
        return context_report.timeline_json(session, run)
    except Exception as exc:  # a missing conversation is a normal answer, not a 500
        return {"conversation_id": session, "run": run, "turns": [], "error": f"{type(exc).__name__}: {exc}"}


@router.get("/handoff")
def handoff(session: str = Query(..., min_length=1), run: Optional[str] = None,
            recent: int = Query(3, ge=1, le=20)) -> dict[str, Any]:
    """The compact sidecar the CLI export prints — latest judgments, changes, patterns."""
    context_report = _mod("context_report")
    try:
        return context_report.handoff(session, run, recent)
    except Exception as exc:
        return {"conversation_id": session, "error": f"{type(exc).__name__}: {exc}"}


class SettingsPayload(BaseModel):
    contextual: bool
    context_window: int = Field(ge=0, le=12)
    open_corrections: int = Field(ge=0, le=6)


@router.post("/settings")
def save_settings(payload: SettingsPayload) -> dict[str, Any]:
    """Persist the three observer knobs through the canonical plugin-settings writer."""
    from hermes_cli.plugins_state import save_plugin_setting

    for key, value in (("contextual", payload.contextual),
                       ("context_window", payload.context_window),
                       ("open_corrections", payload.open_corrections)):
        save_plugin_setting("jev-observer", (key,), value)

    return {"settings": _mod("settings").current()}


class TestPayload(BaseModel):
    text: str = Field(min_length=1, max_length=8_000)


@router.post("/test")
def test_reply(payload: TestPayload) -> dict[str, Any]:
    """One live Jev call on arbitrary text — the fastest "is it working?" check.

    Same provider/key resolution and same reply-only rubric as a captured
    exchange, so a passing test means the live path works. Nothing is stored.
    """
    worker = _mod("worker")
    provider, key = worker._resolve()
    if provider is None or not key:
        return {"ok": False, "error": "No Jev key configured. Add a TypeSafe or DefAPI key in Settings ▸ Providers."}

    observation = worker._observe(payload.text, "manual-test", provider, key)
    states = observation.get("states") or {}
    ranked = sorted(((k, float(v)) for k, v in states.items() if isinstance(v, (int, float))),
                    key=lambda kv: kv[1], reverse=True)
    return {"ok": True, "provider": provider.get("name"), "observer": observation.get("observer"),
            "states": states, "ranked": ranked, "count": len(ranked)}


class RescorePayload(BaseModel):
    session: str = Field(min_length=1)
    limit: Optional[int] = Field(default=None, ge=1, le=500)


@router.post("/rescore")
def rescore(payload: RescorePayload) -> dict[str, Any]:
    """Re-judge a conversation under the CURRENT settings, in a background run.

    Each re-run gets its own ``rescore-<timestamp>`` label, so earlier rows are
    untouched and both runs stay comparable in the timeline. This is how a
    settings change is observed: change the knobs, re-score, compare runs.
    """
    context_report = _mod("context_report")
    worker = _mod("worker")
    run, queued = context_report.rescore(payload.session, payload.limit)
    if queued:
        threading.Thread(target=worker.drain_run, args=(payload.session, run), daemon=True,
                         name=f"jev-rescore-{run}").start()
    return {"run": run, "queued": int(queued),
            "message": ("Queued. Judgments appear under this run as they finish."
                        if queued else "Nothing to re-score for this conversation.")}


class ClearPayload(BaseModel):
    session: Optional[str] = None
    confirm: bool = False


@router.post("/clear")
def clear(payload: ClearPayload) -> dict[str, Any]:
    """Delete observations (one conversation, or all) after backing up the database.

    Writes the backup with SQLite's online backup API — WAL-safe while the
    observer may be writing — then deletes context rows first so nothing is
    orphaned.
    """
    if not payload.confirm:
        return {"cleared": False, "error": "confirm must be true"}

    store = _mod("store")
    from plugins.plugin_storage import plugin_data_dir
    import sqlite3
    from datetime import datetime, timezone

    data_dir = plugin_data_dir("jev-observer")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = data_dir / f"data.db.bak-{stamp}"

    conn = store.connect()
    try:
        backup = sqlite3.connect(str(backup_path))
        try:
            conn.backup(backup)
        finally:
            backup.close()

        where, args = "", ()
        if payload.session:
            where, args = " WHERE session_id=?", (payload.session,)

        context_deleted = conn.execute(f"DELETE FROM context_observations{where}", args).rowcount
        observations_deleted = conn.execute(f"DELETE FROM observations{where}", args).rowcount
        conn.commit()
    finally:
        conn.close()

    return {"cleared": True, "context_rows": int(context_deleted), "observations": int(observations_deleted),
            "backup": str(backup_path), "scope": payload.session or "all"}

