"""Thoth never probes local ports for Ollama or LM Studio: a running server only appears in the
model picker once the user adds it under Custom Endpoints, and nothing is written to config."""

import hermes_cli.providers as providers_mod
import pytest
from hermes_cli.model_switch import list_authenticated_providers


@pytest.fixture
def local_servers_up(monkeypatch):
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", dict)
    monkeypatch.setattr(providers_mod, "HERMES_OVERLAYS", {})
    monkeypatch.delenv("LM_BASE_URL", raising=False)
    monkeypatch.delenv("LM_API_KEY", raising=False)
    probes: list[str] = []

    def _lmstudio(api_key=None, base_url=None, timeout=5.0):
        probes.append(f"lmstudio {base_url}")
        return ["qwen3-8b"]

    def _ollama(base_url, *a, **k):
        probes.append(f"ollama {base_url}")
        return ["mistral-nemo:12b"]

    monkeypatch.setattr("hermes_cli.models_local.fetch_lmstudio_models", _lmstudio)
    monkeypatch.setattr("hermes_cli.models_local.fetch_ollama_local_models", _ollama)
    saved: list = []
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {"custom_providers": []})
    monkeypatch.setattr("hermes_cli.config.save_config", saved.append)
    return probes, saved


def test_running_local_servers_are_not_listed_or_saved(local_servers_up):
    probes, saved = local_servers_up

    providers = list_authenticated_providers(
        current_provider="openrouter", current_base_url="https://openrouter.ai/api/v1", custom_providers=[])

    names = {p["slug"] for p in providers} | {p["name"].lower() for p in providers}
    assert "lmstudio" not in names and "ollama" not in names
    assert probes == [] and saved == []


def test_ollama_added_as_custom_endpoint_is_listed(local_servers_up):
    configured = [{"name": "Ollama", "base_url": "http://127.0.0.1:11434/v1", "models": ["llama3"]}]

    providers = list_authenticated_providers(
        current_provider="openrouter", current_base_url="https://openrouter.ai/api/v1", custom_providers=configured)

    assert [p["name"] for p in providers if "ollama" in p["name"].lower()] == ["Ollama"]
