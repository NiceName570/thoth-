"""Contract for ``/api/local-models/ollama``: the desktop's Local Models pane lists the user's own
Ollama library (native ``/api/tags``) against a real loopback server, never a live Ollama."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient


class _TagsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/tags":
            self.send_error(404)
            return
        body = json.dumps({"models": [{"name": "llama3.2:3b", "model": "llama3.2:3b"},
                                      {"name": "qwen3:8b", "model": "qwen3:8b"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def ollama_root():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TagsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _client(tmp_path, monkeypatch, host: str, config: dict | None = None) -> TestClient:
    home = tmp_path / ".hermes"
    home.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (home / "config.yaml").write_text(json.dumps(config), encoding="utf-8")  # JSON is valid YAML
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("OLLAMA_HOST", host)
    from hermes_cli import web_server

    client = TestClient(web_server.app)
    client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
    return client


def test_lists_the_ollama_library_and_marks_the_active_model(tmp_path, monkeypatch, ollama_root):
    config = {"model": {"provider": "custom", "base_url": f"{ollama_root}/v1", "default": "qwen3:8b"}}
    client = _client(tmp_path, monkeypatch, ollama_root, config)

    data = client.get("/api/local-models/ollama").json()

    assert data["reachable"] is True
    assert data["models"] == ["llama3.2:3b", "qwen3:8b"]
    assert data["base_url"] == f"{ollama_root}/v1"
    assert data["active_model"] == "qwen3:8b"


def test_a_wildcard_ollama_host_is_reached_over_loopback(tmp_path, monkeypatch, ollama_root):
    """``OLLAMA_HOST=0.0.0.0:<port>`` (Ollama serving the LAN) is the bind address, not a dialable one."""
    port = ollama_root.rsplit(":", 1)[1]
    client = _client(tmp_path, monkeypatch, f"0.0.0.0:{port}")

    data = client.get("/api/local-models/ollama").json()

    assert data["reachable"] is True
    assert data["models"] == ["llama3.2:3b", "qwen3:8b"]
    assert data["base_url"] == f"http://127.0.0.1:{port}/v1"


class _ResidentHandler(BaseHTTPRequestHandler):
    """``/api/ps`` lists resident models; ``/api/generate`` with ``keep_alive: 0`` unloads one."""
    resident: list[str] = []

    def do_GET(self):
        if self.path != "/api/ps":
            self.send_error(404)
            return
        self._json({"models": [{"name": name, "model": name} for name in type(self).resident]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path != "/api/generate" or body.get("keep_alive") != 0:
            self.send_error(400)
            return
        type(self).resident = [name for name in type(self).resident if name != body["model"]]
        self._json({"done": True})

    def _json(self, payload):
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def resident_ollama_port():
    _ResidentHandler.resident = ["qwen3:8b", "llama3.2:3b"]
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ResidentHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def test_eject_unloads_every_resident_model_from_a_wildcard_host(tmp_path, monkeypatch, resident_ollama_port):
    client = _client(tmp_path, monkeypatch, f"0.0.0.0:{resident_ollama_port}")

    data = client.post("/api/local-models/ollama/eject").json()

    assert data == {"ok": True, "ejected": ["qwen3:8b", "llama3.2:3b"]}
    assert _ResidentHandler.resident == []


def test_eject_roots_are_loopback_only(tmp_path, monkeypatch):
    """A remote provider or a shared LAN Ollama is never probed or unloaded by an eject."""
    from hermes_cli.models_local import configured_ollama_roots

    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:11434")
    config = {"model": {"provider": "custom", "base_url": "https://api.openai.com/v1"},
              "custom_providers": [{"name": "lan", "base_url": "http://192.168.1.20:11434/v1"},
                                   {"name": "wild", "base_url": "http://0.0.0.0:22434/v1"}]}

    assert configured_ollama_roots(config) == ["http://127.0.0.1:11434", "http://127.0.0.1:22434"]


def test_reports_unreachable_when_nothing_listens(tmp_path, monkeypatch):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    client = _client(tmp_path, monkeypatch, f"http://127.0.0.1:{port}")

    data = client.get("/api/local-models/ollama").json()

    assert data == {"reachable": False, "base_url": f"http://127.0.0.1:{port}/v1", "models": [],
                    "active_model": None}
