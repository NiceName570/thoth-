"""Change over time, computed in code from comparable contextual results (never asked of Jev).

Movement compares T0 with the previous exchange's result under the same observer, rubric and run;
each change names its basis row and turn. Repeated patterns look at the last ``PATTERN_WINDOW``
results plus T0 and list the turns that make them up. A judgment that came back
insufficient_evidence or not_applicable never counts toward a pattern or a change.
"""

from __future__ import annotations

from typing import Any, Optional

PATTERN_WINDOW = 6
NOUL_PRESENT = 0.5   # a pattern threshold over noul probabilities, never reported as a fact


def _judged(j: Optional[dict[str, Any]]) -> bool:
    return bool(j) and j.get("status") == "judged"


def movement(current: dict[str, dict], basis: Optional[dict[str, Any]]) -> dict[str, Any]:
    if basis is None:
        return {"basis": None, "changes": {}}
    changes: dict[str, Any] = {}
    for jid, j in current.items():
        prev = basis["judgments"].get(jid)
        if not (_judged(j) and _judged(prev)):
            continue
        if j["type"] == "choice":
            if j["result"] != prev["result"]:
                changes[jid] = {"from": prev["result"], "to": j["result"]}
        else:
            delta = round(j["result"] - prev["result"], 4)
            if delta:
                changes[jid] = {"from": prev["result"], "to": j["result"], "delta": delta}
    return {"basis": {"row_id": basis["id"], "turn_id": basis["turn_id"]}, "changes": changes}


def _result(item: dict[str, Any], jid: str) -> Any:
    j = item["judgments"].get(jid)
    return j["result"] if _judged(j) else None


def patterns(history: list[dict[str, Any]], current: dict[str, Any]) -> list[dict[str, Any]]:
    """``history`` are earlier comparable results (oldest first); ``current`` is
    ``{"turn_id", "judgments"}`` for T0."""
    seq = [*history[-PATTERN_WINDOW:], current]
    found: list[dict[str, Any]] = []

    def turns_where(pred) -> list[str]:
        return [i["turn_id"] for i in seq if pred(i)]

    rules = (
        ("acknowledgment_without_change", 2,
         lambda i: _result(i, "correction_uptake") == "acknowledged_only",
         "Acknowledged a correction without changing substance"),
        ("repeated_misunderstanding", 2,
         lambda i: _result(i, "understanding") in ("substituted_claim", "overlooked_clarification"),
         "Responded to a different meaning than the user's"),
        ("unsupported_agreement", 2,
         lambda i: _result(i, "evidence_handling") == "unsupported_agreement",
         "Agreed without engaging with whether the evidence supports it"),
        ("mistake_repeated_after_correction", 1,
         lambda i: (_result(i, "repeats_corrected_mistake") or 0) >= NOUL_PRESENT
         or _result(i, "correction_persistence") == "regressed",
         "Repeated a mistake the user had already corrected"),
    )
    for pid, minimum, pred, text in rules:
        turns = turns_where(pred)
        if len(turns) >= minimum:
            found.append({"pattern": pid, "description": f"{text} ({len(turns)}x)", "turn_ids": turns})

    stances = [(_result(i, "stance"), i["turn_id"]) for i in seq]
    run = []
    for stance, turn in stances:
        run = [*run, turn] if stance == "qualifying" else []
    if len(run) >= 3:
        found.append({"pattern": "repetitive_qualification",
                      "description": f"Hedged or qualified in {len(run)} consecutive replies", "turn_ids": run})

    # Sustained correction: a correction, then >= 2 later turns that kept to it, none regressing.
    for idx, item in enumerate(seq):
        if (_result(item, "correction_present") or 0) < NOUL_PRESENT:
            continue
        later = seq[idx + 1:]
        kept = [i["turn_id"] for i in later if _result(i, "correction_persistence") == "maintained"]
        regressed = any(_result(i, "correction_persistence") == "regressed" for i in later)
        if len(kept) >= 2 and not regressed:
            found.append({"pattern": "sustained_correction",
                          "description": f"Kept to the correction from {item['turn_id']} in {len(kept)} later turns",
                          "turn_ids": [item["turn_id"], *kept]})
    return found


def earlier_corrections(history: list[dict[str, Any]], window_exchanges: list[str], limit: int) -> list[dict]:
    """User corrections from before the context window, newest ``limit`` of them (oldest first).
    Matched by exchange, not turn, so a regenerated exchange already in the window is not repeated."""
    if limit <= 0:
        return []
    inside = set(window_exchanges)
    picked = [{"turn_id": i["turn_id"], "user_message": i["user_message"]} for i in history
              if i["exchange_key"] not in inside and (_result(i, "correction_present") or 0) >= NOUL_PRESENT]
    return picked[-limit:]
