"""Compatibility for Microsoft's October 2026 Edge speech endpoint migration."""

from __future__ import annotations

import importlib
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit


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
    token = parse_qs(current.query)["TrustedClientToken"][0]
    communication.WSS_URL = (
        "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1?"
        + urlencode({"Ocp-Apim-Subscription-Key": token})
    )
