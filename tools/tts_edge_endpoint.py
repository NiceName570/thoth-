"""Compatibility for Microsoft's October 2026 Edge speech endpoint migration."""

from __future__ import annotations

import asyncio
import importlib
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlsplit

# The replacement host answers a burst of handshakes with 429; read-aloud opens one connection per
# chunk, so roughly every other chunk was refused. A short wait clears it.
EDGE_THROTTLE_RETRY_DELAYS = (0.5, 1.0, 2.0)


async def save_edge_speech(make_communicate: Callable[[], Any], output_path: str) -> None:
    """Save speech with bounded retries on the endpoint's 429 handshake throttle. Each attempt
    builds a fresh ``Communicate``: the SDK refuses to stream the same instance twice."""
    for delay in (*EDGE_THROTTLE_RETRY_DELAYS, None):
        try:
            await make_communicate().save(output_path)
            return
        except Exception as exc:
            if delay is None or getattr(exc, "status", None) != 429:
                raise
        await asyncio.sleep(delay)


def configure_edge_synthesis_endpoint(sdk: Any) -> None:
    """Migrate only the old SDK synthesis URL; leave voice discovery unchanged.

    edge-tts 7.2.7/7.2.8 still target the Bing synthesis host, which now returns
    403. Match the upstream fix in rany2/edge-tts#491 without modifying a PM-owned
    installation. A newer SDK's endpoint is already authoritative and stays intact.
    """
    if getattr(sdk, "__name__", None) != "edge_tts":
        return
    communication = importlib.import_module("edge_tts.communicate")
    current = urlsplit(communication.WSS_URL)
    if current.hostname != "speech.platform.bing.com":
        return
    token = next(iter(parse_qs(current.query).get("TrustedClientToken", [])), "")
    if not token:
        return
    communication.WSS_URL = (
        "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1?"
        + urlencode({"Ocp-Apim-Subscription-Key": token})
    )
