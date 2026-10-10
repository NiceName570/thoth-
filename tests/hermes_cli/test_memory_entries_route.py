"""Contract: the Memories page lists, edits and deletes MEMORY.md / USER.md entries on disk.

Real router via TestClient against a temp HERMES_HOME."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

DELIM = "\n§\n"


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    (home / "memories").mkdir(parents=True)
    (home / "memories" / "MEMORY.md").write_text(DELIM.join(["Project lives in Desktop/Thoth", "Use Ollama for quick chats"]), encoding="utf-8")
    (home / "memories" / "USER.md").write_text("Prefers terse answers", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


@pytest.fixture
def client(home):
    from hermes_cli import web_server

    test_client = TestClient(web_server.app)
    test_client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
    return test_client


def test_lists_both_memory_files(client):
    body = client.get("/api/memory/entries").json()

    assert body["memory"]["entries"] == ["Project lives in Desktop/Thoth", "Use Ollama for quick chats"]
    assert body["user"]["entries"] == ["Prefers terse answers"]
    assert body["memory"]["limit"] > 0


def test_edit_rewrites_only_that_entry(client, home):
    r = client.post("/api/memory/entries", json={
        "target": "memory", "entry": "Use Ollama for quick chats", "content": "Use Codex by default"})

    assert r.status_code == 200
    assert r.json()["entries"] == ["Project lives in Desktop/Thoth", "Use Codex by default"]
    assert "Use Codex by default" in (home / "memories" / "MEMORY.md").read_text(encoding="utf-8")


def test_delete_removes_the_entry_from_disk(client, home):
    r = client.post("/api/memory/entries", json={"target": "user", "entry": "Prefers terse answers"})

    assert r.status_code == 200 and r.json()["entries"] == []
    assert "Prefers terse answers" not in (home / "memories" / "USER.md").read_text(encoding="utf-8")


def test_stale_entry_is_refused_not_clobbered(client, home):
    r = client.post("/api/memory/entries", json={
        "target": "memory", "entry": "Use Ollama", "content": "overwritten"})

    assert r.status_code == 409
    assert "Use Ollama for quick chats" in (home / "memories" / "MEMORY.md").read_text(encoding="utf-8")
