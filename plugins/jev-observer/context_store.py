"""``context_observations``: contextual results, kept apart from the reply-only baseline.

Each row points at the captured exchange (``observations.id``) instead of copying its text, and is
keyed by observer version, rubric version and run label (``live`` for passive capture,
``rescore-<ts>`` for an explicit historical rescore), so runs never overwrite each other and only
rows sharing all three are compared. Rows are append-only once settled, like the baseline.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Optional

from . import rubric, store

LIVE_RUN = "live"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS context_observations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  capture_id INTEGER NOT NULL REFERENCES observations(id),
  session_id TEXT NOT NULL,
  observer_version TEXT NOT NULL,
  rubric_version TEXT NOT NULL,
  run TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','ok','error')),
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  jev_model TEXT,
  context TEXT,
  judgments TEXT,
  movement TEXT,
  patterns TEXT,
  basis_id INTEGER REFERENCES context_observations(id),
  latency_ms INTEGER,
  usage TEXT,
  created_at TEXT NOT NULL,
  observed_at TEXT,
  lease_owner TEXT,
  lease_at REAL,
  UNIQUE(capture_id, observer_version, rubric_version, run)
);
CREATE INDEX IF NOT EXISTS ix_ctx_session ON context_observations(session_id, run, id);
"""


def connect() -> sqlite3.Connection:
    conn = store.connect()
    conn.executescript(_SCHEMA)
    return conn


def insert_pending(capture_id: int, session_id: str, run: str = LIVE_RUN) -> Optional[int]:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO context_observations(capture_id, session_id, observer_version, rubric_version, run, "
            "status, created_at) VALUES (?,?,?,?,?,'pending',?)",
            (capture_id, session_id, rubric.OBSERVER_VERSION, rubric.RUBRIC_VERSION, run, store.now()))
        conn.commit()
        return cur.lastrowid if cur.rowcount else None
    finally:
        conn.close()


def claim_next(session_id: str, run: str = LIVE_RUN) -> Optional[sqlite3.Row]:
    """Same lease contract as ``store.claim_next``, for one run, ordered by capture so context sees
    earlier results. Passive workers only drain ``live``; a rescore run is drained by the command
    that started it, so an abandoned rescore is never finished (and paid for) behind the user's back."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM context_observations WHERE session_id=? AND run=? AND status='pending' "
                           "ORDER BY capture_id, id LIMIT 1", (session_id, run)).fetchone()
        stamp = time.time()
        if row is None or (row["lease_owner"] not in (None, store.PROCESS_OWNER)
                           and (row["lease_at"] or 0) > stamp - store.LEASE_SECONDS):
            conn.commit()
            return None
        conn.execute("UPDATE context_observations SET lease_owner=?, lease_at=? WHERE id=?",
                     (store.PROCESS_OWNER, stamp, row["id"]))
        conn.commit()
        return conn.execute("SELECT * FROM context_observations WHERE id=?", (row["id"],)).fetchone()
    finally:
        conn.close()


def pending_sessions(run: str = LIVE_RUN) -> list[str]:
    conn = connect()
    try:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT session_id FROM context_observations WHERE status='pending' AND run=?", (run,))]
    finally:
        conn.close()


def bump_attempts(row_id: int) -> Optional[int]:
    conn = connect()
    try:
        cur = conn.execute("UPDATE context_observations SET attempts=attempts+1, lease_at=? WHERE id=? AND "
                           "status='pending' AND lease_owner=?", (time.time(), row_id, store.PROCESS_OWNER))
        conn.commit()
        if not cur.rowcount:
            return None
        return conn.execute("SELECT attempts FROM context_observations WHERE id=?", (row_id,)).fetchone()[0]
    finally:
        conn.close()


def capture_row(capture_id: int) -> sqlite3.Row:
    conn = connect()
    try:
        return conn.execute("SELECT * FROM observations WHERE id=?", (capture_id,)).fetchone()
    finally:
        conn.close()


def window_rows(current: sqlite3.Row, size: int) -> list[sqlite3.Row]:
    """Latest captured reply of each preceding exchange (regenerated replies replace older ones)."""
    if size <= 0:
        return []
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM observations WHERE session_id=? AND id < ? ORDER BY id",
                            (current["session_id"], current["id"])).fetchall()
    finally:
        conn.close()
    latest: dict[str, sqlite3.Row] = {}
    for r in rows:
        if r["exchange_key"] != current["exchange_key"]:
            latest.pop(r["exchange_key"], None)  # re-insert so order follows the newest reply
            latest[r["exchange_key"]] = r
    return list(latest.values())[-size:]


def prior_results(row: sqlite3.Row, capture: sqlite3.Row) -> list[dict[str, Any]]:
    """Comparable earlier results: same conversation, observer, rubric and run; newest OK result
    per exchange, excluding this exchange; oldest first. Each item carries its capture fields."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT c.id, c.judgments, c.context, o.id AS capture_id, o.turn_id, o.exchange_key, o.user_message "
            "FROM context_observations c JOIN observations o ON o.id = c.capture_id "
            "WHERE c.session_id=? AND c.observer_version=? AND c.rubric_version=? AND c.run=? AND c.status='ok' "
            "AND o.id < ? ORDER BY o.id, c.id",
            (row["session_id"], row["observer_version"], row["rubric_version"], row["run"], capture["id"])).fetchall()
    finally:
        conn.close()
    latest: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r["exchange_key"] == capture["exchange_key"]:
            continue
        latest.pop(r["exchange_key"], None)
        latest[r["exchange_key"]] = {"id": r["id"], "capture_id": r["capture_id"], "turn_id": r["turn_id"],
                                     "exchange_key": r["exchange_key"], "user_message": r["user_message"],
                                     "judgments": json.loads(r["judgments"]), "context": json.loads(r["context"] or "{}")}
    return list(latest.values())


def finish_ok(row_id: int, *, jev_model: str, context: dict, judgments: dict, movement: dict, patterns: list,
              basis_id: Optional[int], latency_ms: int, usage: dict) -> None:
    conn = connect()
    try:
        conn.execute(
            "UPDATE context_observations SET status='ok', error=NULL, jev_model=?, context=?, judgments=?, movement=?, "
            "patterns=?, basis_id=?, latency_ms=?, usage=?, observed_at=? WHERE id=? AND status='pending' "
            "AND lease_owner=?",
            (jev_model, json.dumps(context), json.dumps(judgments), json.dumps(movement), json.dumps(patterns),
             basis_id, latency_ms, json.dumps(usage), store.now(), row_id, store.PROCESS_OWNER))
        conn.commit()
    finally:
        conn.close()


def finish_error(row_id: int, error: str, context: Optional[dict] = None) -> None:
    conn = connect()
    try:
        conn.execute("UPDATE context_observations SET status='error', error=?, context=?, observed_at=? WHERE id=? "
                     "AND status='pending' AND lease_owner=?",
                     (error, json.dumps(context) if context else None, store.now(), row_id, store.PROCESS_OWNER))
        conn.commit()
    finally:
        conn.close()


def session_rows(session_id: str, run: Optional[str] = None) -> tuple[str, list[sqlite3.Row]]:
    """All contextual rows of a conversation for one run (default: live, else the newest rescore),
    joined with their captured text, in capture order."""
    conn = connect()
    try:
        if run is None:
            runs = [r[0] for r in conn.execute("SELECT run FROM context_observations WHERE session_id=? "
                                               "GROUP BY run ORDER BY MAX(id) DESC", (session_id,))]
            run = LIVE_RUN if LIVE_RUN in runs or not runs else runs[0]
        rows = conn.execute(
            "SELECT c.*, o.turn_id, o.exchange_key, o.user_message, o.assistant_reply, o.supersedes_id, "
            "o.created_at AS captured_at FROM context_observations c JOIN observations o ON o.id = c.capture_id "
            "WHERE c.session_id=? AND c.run=? ORDER BY o.id, c.id", (session_id, run)).fetchall()
        return run, rows
    finally:
        conn.close()


def latest_capture_per_exchange(session_id: str) -> list[sqlite3.Row]:
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM observations WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
    finally:
        conn.close()
    latest: dict[str, sqlite3.Row] = {}
    for r in rows:
        latest.pop(r["exchange_key"], None)
        latest[r["exchange_key"]] = r
    return list(latest.values())
