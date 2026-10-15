"""``hermes jev-observer export|timeline|rescore|check``. Output goes to a file or stdout; nothing is
ever injected into a conversation."""

from __future__ import annotations

import json
from pathlib import Path

from . import context_report, store, worker
from .jev_adapter import handoff


def setup(parser) -> None:
    sub = parser.add_subparsers(dest="jev_action", required=True)
    exp = sub.add_parser("export", help="Compact handoff for one conversation (export only)")
    exp.add_argument("--session", required=True, help="Thoth session id")
    exp.add_argument("--recent", type=int, default=3, help="Observations to summarise (default 3)")
    exp.add_argument("--out", help="Write JSON here instead of stdout")
    exp.add_argument("--observer", choices=("reply", "context"), default="reply",
                     help="reply = jev-reply-v1 baseline (default); context = jev-context-v1")
    exp.add_argument("--run", help="Contextual run label (default: live, else the newest rescore)")
    tl = sub.add_parser("timeline", help="Readable per-turn contextual timeline for one conversation")
    tl.add_argument("--session", required=True, help="Thoth session id")
    tl.add_argument("--run", help="Contextual run label (default: live, else the newest rescore)")
    tl.add_argument("--json", action="store_true", help="Machine-readable timeline")
    tl.add_argument("--out", help="Write here instead of stdout")
    rs = sub.add_parser("rescore", help="Explicitly re-judge a past conversation with the contextual rubric")
    rs.add_argument("--session", required=True, help="Thoth session id")
    rs.add_argument("--limit", type=int, help="Only the most recent N exchanges")
    chk = sub.add_parser("check", help="One live Jev call on a sample reply; prints probabilities")
    chk.add_argument("text", help="Assistant reply text to observe")


def build_handoff(session_id: str, recent: int = 3) -> dict:
    observations = [{
        "turn_id": r["turn_id"],
        "states": json.loads(r["probabilities"]),
        "triggers": [],
        "direction": "unknown",
        "evidence": [r["assistant_reply"][:240]],  # same evidence convention as iteration_pipeline --live
        "observer": r["jev_model"],
        "source": "assistant_reply",
    } for r in store.export_rows(session_id)]
    result = handoff(observations, recent=recent)
    result["observer_version"] = store.OBSERVER_VERSION
    result["conversation_id"] = session_id
    return result


def _emit(text: str, out: str | None) -> int:
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {out}")
    else:
        print(text)
    return 0


def _export(args) -> int:
    if args.observer == "context":
        data = context_report.handoff(args.session, args.run, args.recent)
    else:
        data = build_handoff(args.session, args.recent)
    return _emit(json.dumps(data, indent=2), args.out)


def _timeline(args) -> int:
    if args.json:
        return _emit(json.dumps(context_report.timeline_json(args.session, args.run), indent=2), args.out)
    return _emit(context_report.timeline_text(args.session, args.run), args.out)


def _rescore(args) -> int:
    run, queued = context_report.rescore(args.session, args.limit)
    print(f"Queued {queued} exchanges under run {run}; observing now (earlier results are kept).")
    worker.drain_run(args.session, run)
    print(f"Done. View with: hermes jev-observer timeline --session {args.session} --run {run}")
    return 0


def _check(args) -> int:
    provider, key = worker._resolve()
    if provider is None:
        print("No Jev key: add a TypeSafe or DefAPI key in Settings > Providers.")
        return 1
    obs = worker._observe(args.text, "check", provider, key)
    print(json.dumps({"provider": provider["name"], "observer": obs.get("observer"), "states": obs["states"]},
                     indent=2, sort_keys=True))
    return 0


def handle(args) -> int:
    return {"export": _export, "timeline": _timeline, "rescore": _rescore, "check": _check}[args.jev_action](args)
