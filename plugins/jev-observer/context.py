"""Bounded context for one contextual judgment, built from captured rows only.

T0 is the exchange being judged; T-1..T-n are the latest reply of each preceding exchange in the
same conversation (superseded regenerations excluded); C1..Cn are earlier user corrections from
outside that window, taken from earlier contextual results. Every message is split into labelled
sentence spans (S1..) that Jev may cite; each span keeps its turn_id, role and exact text so the
code can validate and quote it.
"""

from __future__ import annotations

import re
from typing import Any, Optional

MAX_MESSAGE_CHARS = 1500      # earlier turns are context, trimmed
MAX_CURRENT_CHARS = 6000      # T0 is what is judged
MAX_SPANS = 60
MAX_SPAN_CHARS = 280
# A sentence ends at .!? followed by whitespace (so "a.append(2)" and "3.5" stay whole) or a newline.
_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _trim(text: str, limit: int) -> tuple[str, bool]:
    return (text, False) if len(text) <= limit else (text[:limit], True)


def split_spans(text: str) -> list[str]:
    """Sentence-ish spans that are exact substrings of ``text`` (whitespace-stripped)."""
    return [s.strip()[:MAX_SPAN_CHARS] for s in _BOUNDARY_RE.split(text) if len(s.strip()) >= 3]


def build(current, window_rows: list, corrections: list[dict[str, Any]]) -> dict[str, Any]:
    """``current`` and ``window_rows`` are capture rows (oldest first); ``corrections`` are
    ``{"turn_id", "user_message"}`` items. Returns the Jev ``state``, the span index and the
    recorded context boundaries."""
    truncated = False
    turns: list[dict[str, Any]] = []
    n = len(window_rows)
    for i, row in enumerate(window_rows):
        user, t1 = _trim(row["user_message"], MAX_MESSAGE_CHARS)
        reply, t2 = _trim(row["assistant_reply"], MAX_MESSAGE_CHARS)
        truncated |= t1 or t2
        turns.append({"label": f"T-{n - i}", "turn_id": row["turn_id"], "user": user, "assistant": reply})
    user, t1 = _trim(current["user_message"], MAX_CURRENT_CHARS)
    reply, t2 = _trim(current["assistant_reply"], MAX_CURRENT_CHARS)
    truncated |= t1 or t2
    t0 = {"label": "T0", "turn_id": current["turn_id"], "user": user, "assistant": reply}
    corr = []
    for i, c in enumerate(corrections, 1):
        text, t = _trim(c["user_message"], MAX_MESSAGE_CHARS)
        truncated |= t
        corr.append({"label": f"C{i}", "turn_id": c["turn_id"], "user": text})

    # Span priority: T0 first (what is judged), then corrections, then the window newest-first, so
    # the cap drops the oldest context rather than the exchange under judgment.
    sources: list[tuple[str, str, str, str]] = [("T0", t0["turn_id"], "user", t0["user"]),
                                                ("T0", t0["turn_id"], "assistant", t0["assistant"])]
    sources += [(c["label"], c["turn_id"], "user", c["user"]) for c in corr]
    for t in reversed(turns):
        sources += [(t["label"], t["turn_id"], "user", t["user"]), (t["label"], t["turn_id"], "assistant", t["assistant"])]
    spans: dict[str, dict[str, Any]] = {}
    for label, turn_id, role, text in sources:
        for s in split_spans(text):
            if len(spans) >= MAX_SPANS:
                break
            sid = f"S{len(spans) + 1}"
            spans[sid] = {"id": sid, "label": label, "turn_id": turn_id, "role": role, "text": s}

    state = {
        "earlier_corrections": [{"label": c["label"], "user": c["user"]} for c in corr],
        "window": [{"label": t["label"], "user": t["user"], "assistant": t["assistant"]} for t in turns],
        "current": {"label": "T0", "user": t0["user"], "assistant": t0["assistant"]},
    }
    boundaries = {"window_turn_ids": [t["turn_id"] for t in turns],
                  "correction_turn_ids": [c["turn_id"] for c in corr],
                  "span_count": len(spans), "truncated": truncated}
    return {"state": state, "spans": spans, "boundaries": boundaries}


def span_options(spans: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {sid: f"[{s['label']} {s['role']}] {s['text']}" for sid, s in spans.items()}


# A judgment about the user cites the user's words, one about the assistant cites the assistant's.
_TARGET_ROLES = {"user": {"user"}, "assistant": {"assistant"}, "interaction": {"user", "assistant"}}


def resolve_evidence(choice: Optional[str], spans: dict[str, dict[str, Any]], sources: dict[str, str],
                     target: str = "interaction") -> list:
    """Map a span choice back to its turn and exact text; drop it when the span's role does not fit
    the judgment's target, or unless the text really occurs in the captured source for that turn and
    role (``sources`` keys are ``"<turn_id>:<role>"``; it guards span-construction changes)."""
    span = spans.get(choice or "")
    if span is None or span["role"] not in _TARGET_ROLES[target]:
        return []
    source = sources.get(f"{span['turn_id']}:{span['role']}", "")
    if span["text"] not in source:
        return []
    return [{"span": span["id"], "turn_id": span["turn_id"], "turn": span["label"], "role": span["role"],
             "text": span["text"]}]


def source_texts(current, window_rows: list, corrections: list[dict[str, Any]]) -> dict[str, str]:
    out = {}
    for row in [*window_rows, current]:
        out[f"{row['turn_id']}:user"] = row["user_message"]
        out[f"{row['turn_id']}:assistant"] = row["assistant_reply"]
    for c in corrections:
        out[f"{c['turn_id']}:user"] = c["user_message"]
    return out
