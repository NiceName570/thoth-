"""``hermes jev-observer export|check``. Export only writes a file or stdout; nothing is injected."""

from __future__ import annotations

import json
from pathlib import Path

from . import store, worker
from .jev_adapter import handoff


def setup(parser) -> None:
    sub = parser.add_subparsers(dest="jev_action", required=True)
    exp = sub.add_parser("export", help="Compact handoff for one conversation (export only)")
    exp.add_argument("--session", required=True, help="Thoth session id")
    exp.add_argument("--recent", type=int, default=3, help="Observations to summarise (default 3)")
    exp.add_argument("--out", help="Write JSON here instead of stdout")
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


def _export(args) -> int:
    text = json.dumps(build_handoff(args.session, args.recent), indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(text)
    return 0


def _check(args) -> int:
    key = worker._api_key()
    if not key:
        print(f"{worker.KEY_NAME} is not configured.")
        return 1
    obs = worker._observe(args.text, "check", key)
    print(json.dumps({"observer": obs.get("observer"), "states": obs["states"]}, indent=2, sort_keys=True))
    return 0


def handle(args) -> int:
    return {"export": _export, "check": _check}[args.jev_action](args)
