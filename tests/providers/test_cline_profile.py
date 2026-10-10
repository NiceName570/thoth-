"""Contract: a Cline API key (ClinePass or pay-as-you-go) resolves to Cline's OpenAI-compatible API."""

import pytest


@pytest.fixture
def cline_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    (home / ".env").write_text("CLINE_API_KEY=cline-test-key\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("CLINE_API_KEY", "cline-test-key")
    return home


@pytest.mark.parametrize("requested", ["cline", "clinepass"])
def test_cline_key_resolves_to_cline_api(cline_home, requested):
    from hermes_cli.runtime_provider import resolve_runtime_provider

    runtime = resolve_runtime_provider(requested=requested, target_model="cline-pass/glm-5.3")

    assert runtime["provider"] == "cline"
    assert runtime["base_url"].rstrip("/") == "https://api.cline.bot/api/v1"
    assert runtime["api_key"] == "cline-test-key"


def test_clinepass_models_are_offered_without_a_live_catalog():
    from providers import get_provider_profile

    profile = get_provider_profile("clinepass")

    assert profile is not None and profile.name == "cline"
    assert "cline-pass/glm-5.3" in profile.fallback_models


def test_cline_is_offered_as_a_key_provider_before_it_is_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    monkeypatch.delenv("CLINE_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from hermes_cli import web_server

    client = TestClient(web_server.app)
    client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
    providers = client.get(
        "/api/model/options", params={"include_unconfigured": "true", "explicit_only": "false"}
    ).json()["providers"]

    cline = next(p for p in providers if p.get("slug") == "cline")
    assert cline.get("key_env") == "CLINE_API_KEY"
    assert cline.get("auth_type") in (None, "api_key")
