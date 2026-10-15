"""Generic Jev decision call (any typed questions) for the contextual observer.

Same request shape and providers as the vendored baseline client; this one passes the caller's
question map through and returns usage and the serving model so each row can record them.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

TIMEOUT_SECONDS = 90


def decide(state: Any, questions: dict[str, Any], provider: dict[str, str], api_key: str) -> dict[str, Any]:
    payload = json.dumps({"model": provider["model"], "state": state, "questions": questions}).encode("utf-8")
    request = urllib.request.Request(
        provider["endpoint"], data=payload, method="POST",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{provider['endpoint']} returned HTTP {error.code}") from None
    latency_ms = int((time.monotonic() - started) * 1000)
    answers = result.get("answers")
    if not isinstance(answers, dict):
        raise ValueError("Jev response has no answers")
    usage = {k: result["usage"][k] for k in ("input_tokens", "output_tokens", "cost")
             if isinstance(result.get("usage"), dict) and k in result["usage"]}
    return {"answers": answers, "usage": usage, "model": str(result.get("model") or provider["model"]),
            "latency_ms": latency_ms}
