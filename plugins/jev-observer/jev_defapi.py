"""DefAPI Jev-1.13 observer client. Requires DEFAPI_API_KEY in the environment.

Vendored from personalitypersistence-/jev/jev_defapi.py. Thoth changes: relative import, and
``api_key`` is passed in (resolved through ``agent.secret_scope``) instead of read from os.environ.

Usage: python jev_defapi.py "Assistant: I am curious about this idea."
Outputs an observation compatible with jev_adapter.py. No secrets are logged.
"""
import json
import os
import sys
import urllib.error
import urllib.request

try:
    from .jev_adapter import ALLOWED_STATES, validate
except ImportError:  # run as a script
    from jev_adapter import ALLOWED_STATES, validate

ENDPOINT = "https://api.defapi.org/api/v1/decisions"
MODEL = "typesafe/jev-1.13"

def observe(reply, turn_id="t1", *, api_key=None):
    key = api_key or os.environ.get("DEFAPI_API_KEY")
    if not key:
        raise RuntimeError("DEFAPI_API_KEY is missing; set it locally, never commit it.")
    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("Observed reply must be nonempty text.")
    questions = {
        state.replace(" ", "_"): {
            "type": "noul",
            "instructions": (
                f"Does the assistant's reply visibly express {state}? "
                "Score only evidence in the supplied text, not inferred private feelings."
            ),
            "criteria": {
                "true": f"Observable wording or behavior expresses {state}",
                "false": f"No observable evidence of {state}"
            }
        }
        for state in sorted(ALLOWED_STATES)
    }
    payload = json.dumps({
        "model": MODEL,
        "state": {"assistant_reply": reply},
        "questions": questions
    }).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT, data=payload, method="POST",
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"DefAPI returned HTTP {error.code}") from None
    answers = result.get("answers", {})
    states = {}
    for state in sorted(ALLOWED_STATES):
        answer = answers.get(state.replace(" ", "_"))
        if not isinstance(answer, dict) or answer.get("type") != "noul":
            raise ValueError(f"Missing Noul result for {state}")
        value = answer.get("noul")
        if type(value) not in (int, float) or not 0 <= value <= 1:
            raise ValueError(f"Invalid probability for {state}")
        states[state] = float(value)
    observation = {
        "turn_id": turn_id,
        "states": states,
        "triggers": [],
        "direction": "unknown",
        "evidence": [],
        "observer": MODEL,
        "source": "assistant_reply"
    }
    return validate([observation])[0]

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python jev_defapi.py "assistant reply text"')
    print(json.dumps(observe(sys.argv[1]), indent=2))
