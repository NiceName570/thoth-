"""Contract: the Local Models pane finds an Ollama the user already runs.

Real router via TestClient, real loopback HTTP server standing in for Ollama's /api/tags."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    from hermes_cli import web_server

    test_client = TestClient(web_server.app)
    test_client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
    return test_client


@pytest.fixture
def fake_ollama():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/api/tags":
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps({"models": [{"name": "qwen3:32b", "model": "qwen3:32b"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_running_ollama_is_detected_with_its_models(client, fake_ollama, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", f"127.0.0.1:{fake_ollama}")

    data = client.get("/api/local-models/ollama").json()

    assert data == {
        "detected": True,
        "base_url": f"http://127.0.0.1:{fake_ollama}/v1",
        "models": ["qwen3:32b"],
    }


def test_no_ollama_reports_not_detected(client, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", f"127.0.0.1:{_free_port()}")

    data = client.get("/api/local-models/ollama").json()

    assert data["detected"] is False
    assert data["models"] == []
