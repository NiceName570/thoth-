"""The Edge voice route serves the whole SDK catalog to the ``tts.edge.voice`` picker."""

from types import SimpleNamespace

import pytest

from tools import tts_tool


@pytest.fixture
def client(monkeypatch):
    from starlette.testclient import TestClient

    from hermes_cli.web_routers import audio
    from hermes_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app

    monkeypatch.setattr(audio, "_edge_voices_cache", [])
    c = TestClient(app)
    c.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return c


def _sdk(voices):
    async def list_voices():
        if isinstance(voices, Exception):
            raise voices
        return voices

    return SimpleNamespace(list_voices=list_voices)


def test_every_catalog_voice_is_listed_english_first(client, monkeypatch):
    catalog = [
        {"ShortName": "fr-FR-DeniseNeural", "Locale": "fr-FR", "LocaleName": "French (France)", "Gender": "Female"},
        {"ShortName": "en-US-AriaNeural", "Locale": "en-US", "LocaleName": "English (United States)", "Gender": "Female"},
        {"ShortName": "af-ZA-AdriNeural", "Locale": "af-ZA", "LocaleName": "Afrikaans (South Africa)", "Gender": "Female"},
        {"Locale": "xx-XX"},
    ]
    monkeypatch.setattr(tts_tool, "_import_edge_tts", lambda: _sdk(catalog))
    body = client.get("/api/audio/edge/voices").json()
    assert body["available"] is True
    ids = [v["voice_id"] for v in body["voices"]]
    assert sorted(ids) == ["af-ZA-AdriNeural", "en-US-AriaNeural", "fr-FR-DeniseNeural"]
    assert ids[0] == "en-US-AriaNeural"
    assert body["voices"][0]["label"] == "Aria (English (United States), Female)"


def test_unreachable_catalog_reports_unavailable(client, monkeypatch):
    monkeypatch.setattr(tts_tool, "_import_edge_tts", lambda: _sdk(OSError("offline")))
    resp = client.get("/api/audio/edge/voices")
    assert resp.status_code == 200
    assert resp.json() == {"available": False, "voices": []}
