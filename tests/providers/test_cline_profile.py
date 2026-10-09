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
