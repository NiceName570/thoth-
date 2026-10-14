"""Independent Jev-style observation adapter. No model calls and no changes to Claude's memory codec.

An external observer produces one JSON object per turn:
{
  "turn_id": "t1",
  "states": {"curiosity": 0.72, "caution": 0.18},
  "triggers": ["new_idea"],
  "direction": "exploring",
  "evidence": ["short, exact quote from the observed reply"],
  "observer": "model/version",
  "source": "assistant_reply"
}

Probabilities describe observable conversational signals, not private feelings.
Run: python jev_adapter.py validate observations.json
     python jev_adapter.py handoff observations.json
"""
import json
import sys
from pathlib import Path

ALLOWED_STATES = {
    "concern", "caution", "curiosity", "enthusiasm", "hesitation",
    "satisfaction", "frustration", "urgency", "amusement", "discomfort",
    "protectiveness", "doubt", "warmth", "humor", "rapport", "appreciation",
    "encouragement", "delight", "pride in the work", "playfulness", "gratitude"
}
MAX_EVIDENCE = 3


def validate(observations):
    if not isinstance(observations, list):
        raise ValueError("Expected a JSON list of turn observations")
    for i, obs in enumerate(observations):
        if not isinstance(obs, dict):
            raise ValueError(f"Observation {i}: expected object")
        if not isinstance(obs.get("turn_id"), str) or not obs["turn_id"]:
            raise ValueError(f"Observation {i}: missing turn_id")
        states = obs.get("states")
        if not isinstance(states, dict):
            raise ValueError(f"Observation {i}: states must be an object")
        for name, p in states.items():
            if name not in ALLOWED_STATES:
                raise ValueError(f"Observation {i}: unknown state {name!r}")
            if type(p) not in (int, float) or not 0 <= p <= 1:
                raise ValueError(f"Observation {i}: {name} must be 0..1")
        if not isinstance(obs.get("triggers", []), list):
            raise ValueError(f"Observation {i}: triggers must be a list")
        if not isinstance(obs.get("evidence", []), list):
            raise ValueError(f"Observation {i}: evidence must be a list")
    return observations


def handoff(observations, recent=3):
    """Small, evidence-linked sidecar; never overwrite Claude's numeric row."""
    observations = validate(observations)
    tail = observations[-recent:]
    latest = tail[-1] if tail else {}
    return {
        "schema": "jev-observer-v1",
        "interpretation": "Probabilities of observed conversational signals, not subjective feelings.",
        "latest_states": latest.get("states", {}),
        "direction": latest.get("direction", "unknown"),
        "recent_triggers": [t for o in tail for t in o.get("triggers", [])][-6:],
        "evidence": [e for o in tail for e in o.get("evidence", [])][-MAX_EVIDENCE:],
        "observer": latest.get("observer", "unknown"),
        "source_turns": [o["turn_id"] for o in tail],
    }


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("validate", "handoff"):
        raise SystemExit("Usage: python jev_adapter.py validate|handoff observations.json")
    observations = validate(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))  # windows-footgun: ok -- vendored verbatim; Thoth never runs this CLI path
    if sys.argv[1] == "validate":
        print(f"Valid: {len(observations)} observations")
    else:
        print(json.dumps(handoff(observations), indent=2))
