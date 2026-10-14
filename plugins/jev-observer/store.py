"""Durable observation records in ``<hermes home>/plugin-data/jev-observer/data.db``.

Rows are append-only: capture inserts a ``pending`` row, the worker finishes it as ``ok`` or
``error``. A regenerated reply is a new row whose ``supersedes_id`` points at the old one; no row
is ever rewritten after it settles or deleted.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

PLUGIN_NAME = "jev-observer"
OBSERVER_VERSION = "jev-reply-v1"  # 21-dimension, reply-only baseline
JEV_MODEL = "typesafe/jev-1.13"  # placeholder until a provider answers; see finish_ok
# Desktop backend, gateway and CLI can share one home; a lease keeps one process per conversation
# queue. Longer than a worst-case row (3 x 40 s timeouts + backoff) so a live worker is never robbed.
LEASE_SECONDS = 300
PROCESS_OWNER = f"{os.getpid()}:{uuid.uuid4().hex[:8]}"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  turn_id TEXT NOT NULL,
  exchange_key TEXT NOT NULL,
  user_message TEXT NOT NULL,
  assistant_reply TEXT NOT NULL,
  reply_sha256 TEXT NOT NULL,
  platform TEXT,
  chat_model TEXT,
  observer_version TEXT NOT NULL,
  jev_model TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','ok','error')),
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  probabilities TEXT,
  deltas TEXT,
  delta_basis_id INTEGER REFERENCES observations(id),
  supersedes_id INTEGER REFERENCES observations(id),
  created_at TEXT NOT NULL,
  observed_at TEXT,
  lease_owner TEXT,
  lease_at REAL,
  UNIQUE(session_id, turn_id, observer_version, reply_sha256)
);
CREATE INDEX IF NOT EXISTS ix_obs_session ON observations(session_id, observer_version, id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def connect() -> sqlite3.Connection:
    """One connection per operation; ``plugin_db`` resolves the home on every call so the store
    follows the active profile."""
    from plugins.plugin_storage import plugin_db
    conn = plugin_db(PLUGIN_NAME)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _text(content: Any) -> str:
    """Flatten multimodal content to its text parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _prior_reply_still_in_history(prior: str, current: str, history: list[dict[str, Any]]) -> bool:
    """A /retry or regenerate removes the old reply; the current reply is the last assistant message,
    dropped first so a byte-identical regeneration is not mistaken for the old reply surviving."""
    replies = [_text(m.get("content")) for m in history if isinstance(m, dict) and m.get("role") == "assistant"]
    for i in range(len(replies) - 1, -1, -1):
        if replies[i] == current:
            del replies[i]
            break
    return prior in replies


def insert_pending(*, session_id: str, turn_id: str, user_message: str, assistant_reply: str,
                   platform: str, chat_model: str, history: list[dict[str, Any]]) -> Optional[int]:
    """Capture one completed exchange. Returns the new row id, or None for a duplicate event."""
    reply_sha = hashlib.sha256(assistant_reply.encode("utf-8")).hexdigest()
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        prev = conn.execute(
            "SELECT id, turn_id, exchange_key, user_message, assistant_reply FROM observations "
            "WHERE session_id=? AND observer_version=? ORDER BY id DESC LIMIT 1",
            (session_id, OBSERVER_VERSION)).fetchone()
        exchange_key, supersedes = turn_id, None
        if (prev is not None and prev["turn_id"] != turn_id and prev["user_message"] == user_message
                and not _prior_reply_still_in_history(prev["assistant_reply"], assistant_reply, history)):
            exchange_key, supersedes = prev["exchange_key"], prev["id"]
        cur = conn.execute(
            "INSERT OR IGNORE INTO observations(session_id, turn_id, exchange_key, user_message, "
            "assistant_reply, reply_sha256, platform, chat_model, observer_version, jev_model, status, "
            "supersedes_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,'pending',?,?)",
            (session_id, turn_id, exchange_key, user_message, assistant_reply, reply_sha, platform,
             chat_model, OBSERVER_VERSION, JEV_MODEL, supersedes, now()))
        conn.commit()
        return cur.lastrowid if cur.rowcount else None
    finally:
        conn.close()


def claim_next(session_id: str) -> Optional[sqlite3.Row]:
    """Lease the oldest pending row of a conversation to this process. None when the queue is empty
    or another live process holds it (that process keeps draining, so order is preserved)."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM observations WHERE session_id=? AND status='pending' ORDER BY id LIMIT 1",
                           (session_id,)).fetchone()
        stamp = time.time()
        if row is None or (row["lease_owner"] not in (None, PROCESS_OWNER)
                           and (row["lease_at"] or 0) > stamp - LEASE_SECONDS):
            conn.commit()
            return None
        conn.execute("UPDATE observations SET lease_owner=?, lease_at=? WHERE id=?", (PROCESS_OWNER, stamp, row["id"]))
        conn.commit()
        return conn.execute("SELECT * FROM observations WHERE id=?", (row["id"],)).fetchone()
    finally:
        conn.close()


def pending_sessions() -> list[str]:
    conn = connect()
    try:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT session_id FROM observations WHERE status='pending'")]
    finally:
        conn.close()


def bump_attempts(row_id: int) -> Optional[int]:
    """Count an attempt and renew the lease; None when this process no longer owns the row."""
    conn = connect()
    try:
        cur = conn.execute("UPDATE observations SET attempts=attempts+1, lease_at=? WHERE id=? AND status='pending' "
                           "AND lease_owner=?", (time.time(), row_id, PROCESS_OWNER))
        conn.commit()
        if not cur.rowcount:
            return None
        return conn.execute("SELECT attempts FROM observations WHERE id=?", (row_id,)).fetchone()[0]
    finally:
        conn.close()


def _latest_ok_per_exchange(conn, session_id: str, observer_version: str, *, before_id: Optional[int] = None,
                            exclude_exchange: Optional[str] = None) -> list[sqlite3.Row]:
    """Newest OK row of each exchange, oldest exchange first: the comparable observation set."""
    rows = conn.execute(
        "SELECT * FROM observations WHERE status='ok' AND session_id=? AND observer_version=? AND id < ? ORDER BY id",
        (session_id, observer_version, before_id if before_id is not None else 2**62)).fetchall()
    latest: dict[str, sqlite3.Row] = {}
    for r in rows:
        if r["exchange_key"] != exclude_exchange:
            latest[r["exchange_key"]] = r
    return sorted(latest.values(), key=lambda r: r["id"])


def finish_ok(row: sqlite3.Row, probabilities: dict[str, float], jev_model: str) -> None:
    """Settle a row as observed. Deltas compare against the latest OK observation of the previous
    exchange in the same conversation and observer version; null when there is none."""
    conn = connect()
    try:
        basis_rows = _latest_ok_per_exchange(conn, row["session_id"], row["observer_version"],
                                             before_id=row["id"], exclude_exchange=row["exchange_key"])
        basis = basis_rows[-1] if basis_rows else None
        deltas = None
        if basis is not None:
            prev = json.loads(basis["probabilities"])
            deltas = {k: (round(v - prev[k], 6) if k in prev else None) for k, v in sorted(probabilities.items())}
        conn.execute(
            "UPDATE observations SET status='ok', jev_model=?, probabilities=?, deltas=?, delta_basis_id=?, error=NULL, "
            "observed_at=? WHERE id=? AND status='pending' AND lease_owner=?",
            (jev_model, json.dumps(probabilities, sort_keys=True), json.dumps(deltas) if deltas is not None else None,
             basis["id"] if basis is not None else None, now(), row["id"], PROCESS_OWNER))
        conn.commit()
    finally:
        conn.close()


def finish_error(row_id: int, error: str) -> None:
    conn = connect()
    try:
        conn.execute("UPDATE observations SET status='error', error=?, observed_at=? WHERE id=? AND status='pending' "
                     "AND lease_owner=?", (error, now(), row_id, PROCESS_OWNER))
        conn.commit()
    finally:
        conn.close()


def export_rows(session_id: str, observer_version: str = OBSERVER_VERSION) -> list[sqlite3.Row]:
    conn = connect()
    try:
        return _latest_ok_per_exchange(conn, session_id, observer_version)
    finally:
        conn.close()
