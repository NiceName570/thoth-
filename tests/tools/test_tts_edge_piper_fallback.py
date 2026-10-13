"""Edge TTS failing falls back to local Piper when it is installed (rany2/edge-tts#490)."""

import json
from pathlib import Path

import pytest

from tools import tts_tool, tts_tool_local
from tools.tts_tool import text_to_speech_tool
from tools.tts_tool_local import DEFAULT_PIPER_VOICE


class _StubPiperVoice:
    @classmethod
    def load(cls, model_path, use_cuda=False):
        return cls()

    def synthesize_wav(self, text, wav_file, syn_config=None):
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x00\x00" * 1024)


def _edge_403(text, file_str, tts_config):
    raise RuntimeError("WSServerHandshakeError: 403, message='Invalid response status'")


@pytest.fixture
def edge_down(tmp_path, monkeypatch):
    tts_tool_local._piper_voice_cache.clear()
    model = tmp_path / f"{DEFAULT_PIPER_VOICE}.onnx"
    model.write_bytes(b"model")
    (tmp_path / f"{DEFAULT_PIPER_VOICE}.onnx.json").write_text("{}")
    monkeypatch.setattr(tts_tool, "_importable", lambda importer: True)
    monkeypatch.setattr(tts_tool, "_run_edge_tts", _edge_403)
    monkeypatch.setattr(tts_tool, "_load_tts_config",
                        lambda: {"provider": "edge", "piper": {"voice": str(model)}})
    yield tmp_path
    tts_tool_local._piper_voice_cache.clear()


def test_edge_failure_speaks_with_piper(edge_down, monkeypatch):
    monkeypatch.setattr(tts_tool, "_import_piper", lambda: _StubPiperVoice)

    data = json.loads(text_to_speech_tool(text="hi", output_path=str(edge_down / "clip.wav")))

    assert data["success"] is True, data
    assert data["provider"] == "piper"
    assert Path(data["file_path"]).stat().st_size > 0


def test_edge_failure_without_piper_reports_the_edge_error(edge_down, monkeypatch):
    monkeypatch.setattr(tts_tool, "_importable", lambda importer: importer is not tts_tool._import_piper)

    data = json.loads(text_to_speech_tool(text="hi", output_path=str(edge_down / "clip.wav")))

    assert data["success"] is False
    assert "403" in data["error"]
