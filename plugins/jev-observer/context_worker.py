"""Contextual observation of one exchange: assemble context, ask Jev, validate, persist.

Runs on the same background worker as the baseline, after it, under the same lease, retry and
error-record rules. Nothing here reaches the conversation.
"""

from __future__ import annotations

import logging
from typing import Any

from . import analysis, context, context_store, rubric, settings, worker

logger = logging.getLogger(__name__)


def _decide(state: Any, questions: dict, provider: dict[str, str], api_key: str) -> dict[str, Any]:
    """Seam for tests."""
    from .jev_client import decide
    return decide(state, questions, provider, api_key)


def _judgments(answers: dict, bundle: dict, sources: dict[str, str]) -> dict[str, dict]:
    out = {}
    for j in rubric.JUDGMENTS:
        parsed = rubric.parse_answer(j, answers.get(j["id"]))
        parsed["evidence"] = []
        ev = answers.get(rubric.evidence_qid(j["id"]))
        if parsed["status"] == "judged" and isinstance(ev, dict) and ev.get("type") == "choice":
            parsed["evidence"] = context.resolve_evidence(ev.get("choice"), bundle["spans"], sources, j["target"])
            if parsed["evidence"]:
                parsed["evidence"][0]["confidence"] = ev.get("confidence")
        out[j["id"]] = parsed
    return out


def _comparable(history: list[dict], cfg: dict) -> list[dict]:
    """Earlier results judged with the same context settings; a mid-conversation change of window
    or carried corrections starts a fresh comparison basis instead of a misleading change."""
    keys = ("context_window", "open_corrections")
    return [h for h in history if all(h["context"].get(k) == cfg[k] for k in keys)]


def _assemble(row) -> dict[str, Any]:
    capture = context_store.capture_row(row["capture_id"])
    cfg = settings.current()
    window = context_store.window_rows(capture, cfg["context_window"])
    history = _comparable(context_store.prior_results(row, capture), cfg)
    corrections = analysis.earlier_corrections(history, [w["exchange_key"] for w in window], cfg["open_corrections"])
    bundle = context.build(capture, window, corrections)
    questions = rubric.build_questions(context.span_options(bundle["spans"]))
    record = {**bundle["boundaries"], "capture_turn_id": capture["turn_id"], "question_count": len(questions),
              "context_window": cfg["context_window"], "open_corrections": cfg["open_corrections"]}
    return {"capture": capture, "history": history, "bundle": bundle, "questions": questions, "record": record,
            "sources": context.source_texts(capture, window, corrections)}


def observe_row(row) -> None:
    if not worker.lifecycle.is_enabled():
        return
    if (row["observer_version"], row["rubric_version"]) != (rubric.OBSERVER_VERSION, rubric.RUBRIC_VERSION):
        # Judging it with today's questions would file the answers under an older rubric.
        context_store.finish_error(row["id"], f"queued for {row['observer_version']}/{row['rubric_version']}, "
                                              f"code is {rubric.OBSERVER_VERSION}/{rubric.RUBRIC_VERSION}; rescore instead")
        return
    provider, key = worker._resolve()
    if provider is None:
        context_store.finish_error(row["id"], "no Jev key: add a TypeSafe or DefAPI key in Settings > Providers")
        return
    try:
        a = _assemble(row)
    except Exception as exc:  # health: allow BLE001 -- a row that cannot be assembled must settle as an error, not block its queue
        context_store.finish_error(row["id"], worker._redact(f"context assembly failed: {type(exc).__name__}: {exc}", key))
        logger.warning("jev-observer context assembly failed for row %s", row["id"], exc_info=True)
        return
    last_error = ""
    attempts = row["attempts"]
    while attempts < worker.MAX_ATTEMPTS:
        if attempts:
            worker._sleep(worker.BACKOFF_SECONDS[min(attempts - 1, len(worker.BACKOFF_SECONDS) - 1)])
        if not worker.lifecycle.is_enabled():
            return
        attempts = context_store.bump_attempts(row["id"])
        if attempts is None:
            return
        if not worker.lifecycle.is_enabled():
            return
        try:
            result = _decide(a["bundle"]["state"], a["questions"], provider, key)
            judgments = _judgments(result["answers"], a["bundle"], a["sources"])
        except Exception as exc:  # health: allow BLE001 -- network, HTTP and malformed answers all become the row's error record
            last_error = worker._redact(f"{type(exc).__name__}: {exc}", key)
            logger.debug("jev-observer context attempt %d for row %s failed: %s", attempts, row["id"], last_error)
            continue
        history, capture = a["history"], a["capture"]
        basis = history[-1] if history else None
        context_store.finish_ok(
            row["id"], jev_model=f'{provider["name"]}:{result["model"]}', context=a["record"], judgments=judgments,
            movement=analysis.movement(judgments, basis),
            patterns=analysis.patterns(history, {"turn_id": capture["turn_id"], "judgments": judgments}),
            basis_id=basis["id"] if basis else None, latency_ms=result["latency_ms"], usage=result["usage"])
        return
    context_store.finish_error(row["id"], last_error or "retry budget exhausted", a["record"])


def drain(session_id: str, run: str = context_store.LIVE_RUN) -> None:
    """Called with the session lock held: by ``worker.drain`` for live rows, by ``rescore`` for its run."""
    while worker.lifecycle.is_enabled() and (row := context_store.claim_next(session_id, run)) is not None:
        observe_row(row)
