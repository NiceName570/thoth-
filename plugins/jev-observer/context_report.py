"""Readable timeline and compact handoff for contextual results (output only, never injected)."""

from __future__ import annotations

import json
from typing import Any

from . import context_store, rubric

# Judgments that headline each timeline turn; the rest appear when they carry evidence or change.
_HEADLINE = ("understanding", "responsiveness", "correction_uptake", "relationship", "turn_success")


def _fmt_result(j: dict[str, Any]) -> str:
    if j["status"] != "judged":
        return j["status"].replace("_", " ")
    if j["type"] == "noul":
        return f"p={j['result']:.2f}"
    if j["type"] == "score":
        return f"{j['result']:.1f}/{j['scale_max']}{' (low confidence)' if j['low_confidence'] else ''}"
    return f"{j['result'].replace('_', ' ')}{' (low confidence)' if j['low_confidence'] else ''}"


def _quote(j: dict[str, Any]) -> str:
    ev = j.get("evidence") or []
    if not ev:
        return ""
    e = ev[0]
    return f'  <- {e["turn"]} {e["role"]} [{e["turn_id"]}]: "{e["text"]}"'


def _row_lines(index: int, row) -> list[str]:
    head = f"#{index} turn {row['turn_id']} · {row['captured_at']}"
    if row["supersedes_id"]:
        head += " · regenerated reply"
    if row["status"] != "ok":
        return [head, f"  {row['status']}: {row['error'] or 'awaiting observation'}"]
    judgments = json.loads(row["judgments"])
    movement = json.loads(row["movement"] or "{}")
    lines = [head, f"  user: {row['user_message'][:160]!r}"]
    changes = movement.get("changes", {})
    for jid in rubric.BY_ID:
        j = judgments.get(jid)
        if j is None:
            continue
        if jid not in _HEADLINE and not j.get("evidence") and jid not in changes:
            continue
        line = f"  {jid} ({j['target']}): {_fmt_result(j)}"
        if jid in changes:
            c = changes[jid]
            was = c["from"].replace("_", " ") if isinstance(c["from"], str) else f"{c['from']:.2f}"
            line += f"  [was {was} at turn {movement['basis']['turn_id']}]"
        lines.append(line + _quote(j))
    for p in json.loads(row["patterns"] or "[]"):
        lines.append(f"  pattern: {p['description']} (turns {', '.join(p['turn_ids'])})")
    ctx = json.loads(row["context"] or "{}")
    lines.append(f"  context: {len(ctx.get('window_turn_ids', []))} prior turns, "
                 f"{len(ctx.get('correction_turn_ids', []))} earlier corrections · {row['latency_ms']} ms · {row['jev_model']}")
    return lines


def timeline_text(session_id: str, run: str | None = None) -> str:
    run, rows = context_store.session_rows(session_id, run)
    if not rows:
        return f"No contextual observations for conversation {session_id}."
    lines = [f"Conversation {session_id} · {rubric.OBSERVER_VERSION} / {rubric.RUBRIC_VERSION} · run {run}",
             "Values are observable-signal judgments, not feelings. p= is a probability; scores are graded levels.", ""]
    for i, row in enumerate(rows, 1):
        lines += [*_row_lines(i, row), ""]
    return "\n".join(lines)


def timeline_json(session_id: str, run: str | None = None) -> dict[str, Any]:
    run, rows = context_store.session_rows(session_id, run)
    return {"conversation_id": session_id, "observer_version": rubric.OBSERVER_VERSION,
            "rubric_version": rubric.RUBRIC_VERSION, "run": run,
            "turns": [{"row_id": r["id"], "turn_id": r["turn_id"], "captured_at": r["captured_at"], "status": r["status"],
                       "error": r["error"], "regenerated": bool(r["supersedes_id"]),
                       "judgments": json.loads(r["judgments"] or "null"), "movement": json.loads(r["movement"] or "null"),
                       "patterns": json.loads(r["patterns"] or "null"), "context": json.loads(r["context"] or "null"),
                       "latency_ms": r["latency_ms"], "usage": json.loads(r["usage"] or "null"), "jev_model": r["jev_model"]}
                      for r in rows]}


def handoff(session_id: str, run: str | None = None, recent: int = 3) -> dict[str, Any]:
    """Compact sidecar: latest judgments with evidence, recent changes, active patterns."""
    run, rows = context_store.session_rows(session_id, run)
    latest: dict[str, Any] = {}
    for r in rows:  # newest OK result per exchange
        if r["status"] == "ok":
            latest.pop(r["exchange_key"], None)
            latest[r["exchange_key"]] = r
    ok = list(latest.values())[-recent:]
    out: dict[str, Any] = {
        "schema": "jev-context-handoff-v1", "observer_version": rubric.OBSERVER_VERSION,
        "rubric_version": rubric.RUBRIC_VERSION, "run": run, "conversation_id": session_id,
        "interpretation": "Typed judgments of observable conversational behaviour, not feelings. Choice/score "
                          "carry Jev confidence; noul values are probabilities.",
        "source_turns": [r["turn_id"] for r in ok]}
    if not ok:
        return out
    last = ok[-1]
    judgments = json.loads(last["judgments"])
    out["latest"] = {jid: {"target": j["target"], "result": j["result"] if j["status"] == "judged" else j["status"],
                           **({"confidence": j["confidence"]} if "confidence" in j else {}),
                           **({"evidence": {k: j["evidence"][0][k] for k in ("turn_id", "text")}} if j["evidence"] else {})}
                     for jid, j in judgments.items()}
    out["changes"] = [{"turn_id": r["turn_id"], "basis_turn_id": m["basis"]["turn_id"], "changes": m["changes"]}
                      for r in ok if (m := json.loads(r["movement"] or "{}")).get("basis") and m["changes"]]
    out["patterns"] = json.loads(last["patterns"] or "[]")
    return out


def rescore(session_id: str, limit: int | None = None) -> tuple[str, int]:
    """Queue an explicit historical rescore under a new run label; earlier rows are untouched."""
    run = f"rescore-{context_store.store.now()}"
    captures = context_store.latest_capture_per_exchange(session_id)
    if limit:
        captures = captures[-limit:]
    queued = sum(context_store.insert_pending(c["id"], session_id, run) is not None for c in captures)
    return run, queued
