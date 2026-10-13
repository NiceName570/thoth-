"""Edge synthesis reaches Microsoft's replacement host without changing voice discovery."""

import asyncio
import sys
from types import ModuleType
from urllib.parse import parse_qs, urlsplit

from tools import tts_tool


def _run_edge(monkeypatch, tmp_path, endpoint):
    sdk = ModuleType("edge_tts")
    communication = ModuleType("edge_tts.communicate")
    communication.WSS_URL = endpoint
    sdk.VOICE_LIST = "https://speech.platform.bing.com/voices/list"
    requests = []

    class Communicate:
        def __init__(self, text, **kwargs):
            requests.append((communication.WSS_URL, text, kwargs))

        async def save(self, path):
            tmp_path.joinpath("speech.mp3").write_bytes(b"audio")

    sdk.Communicate = Communicate
    monkeypatch.setitem(sys.modules, "edge_tts.communicate", communication)
    monkeypatch.setattr(tts_tool, "_import_edge_tts", lambda: sdk)
    output = str(tmp_path / "speech.mp3")
    result = asyncio.run(tts_tool._generate_edge_tts(
        "Hello", output, {"edge": {"voice": "en-US-JennyNeural", "speed": 1.25}}
    ))
    assert result == output
    assert tmp_path.joinpath("speech.mp3").read_bytes() == b"audio"
    assert sdk.VOICE_LIST == "https://speech.platform.bing.com/voices/list"
    return requests[0]


def test_edge_synthesis_uses_replacement_endpoint(monkeypatch, tmp_path):
    endpoint, text, kwargs = _run_edge(
        monkeypatch, tmp_path,
        "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1?TrustedClientToken=test-token",
    )
    parsed = urlsplit(endpoint)
    assert parsed.hostname == "api.msedgeservices.com"
    assert parsed.path == "/tts/cognitiveservices/websocket/v1"
    assert parse_qs(parsed.query) == {"Ocp-Apim-Subscription-Key": ["test-token"]}
    assert text == "Hello"
    assert kwargs == {"voice": "en-US-JennyNeural", "rate": "+25%"}


def test_newer_sdk_endpoint_is_preserved(monkeypatch, tmp_path):
    current = "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1?Ocp-Apim-Subscription-Key=current-token"
    endpoint, _, _ = _run_edge(monkeypatch, tmp_path, current)
    assert endpoint == current
