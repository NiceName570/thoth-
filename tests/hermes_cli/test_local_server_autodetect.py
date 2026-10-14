"""A running LM Studio or Ollama shows up in the model picker with no setup, and a closed port is probed at most
once per TTL window so the picker does not pay the localhost refusal on every open."""

import hermes_cli.model_switch_providers as msp
import hermes_cli.providers as providers_mod
import pytest
from hermes_cli.model_switch import list_authenticated_providers


@pytest.fixture
def lm_probe(monkeypatch):
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", dict)
    monkeypatch.setattr(providers_mod, "HERMES_OVERLAYS", {})
    monkeypatch.delenv("LM_BASE_URL", raising=False)
    monkeypatch.delenv("LM_API_KEY", raising=False)
    monkeypatch.setattr(msp, "_local_autodetect", {})
    calls: list[str] = []
    catalog: list[str] = []

    def _fake_fetch(api_key=None, base_url=None, timeout=5.0):
        calls.append(base_url)
        return list(catalog)

    monkeypatch.setattr("hermes_cli.models_local.fetch_lmstudio_models", _fake_fetch)
    monkeypatch.setattr("hermes_cli.models_local.fetch_ollama_local_models", lambda *a, **k: None)
    return calls, catalog


def _lmstudio_rows():
    providers = list_authenticated_providers(
        current_provider="openrouter", current_base_url="https://openrouter.ai/api/v1")
    return [p for p in providers if p["slug"] == "lmstudio"]


def test_running_lmstudio_is_listed_without_configuration(lm_probe):
    calls, catalog = lm_probe
    catalog.extend(["qwen3-8b", "gemma-3-12b"])

    rows = _lmstudio_rows()

    assert calls == ["http://127.0.0.1:1234/v1"]
    assert len(rows) == 1 and sorted(rows[0]["models"]) == ["gemma-3-12b", "qwen3-8b"]


def test_closed_lmstudio_port_is_probed_once_per_window_and_hidden(lm_probe):
    calls, _catalog = lm_probe

    assert _lmstudio_rows() == []
    assert _lmstudio_rows() == []

    assert len(calls) == 1


@pytest.fixture
def ollama_up(monkeypatch):
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", dict)
    monkeypatch.setattr(providers_mod, "HERMES_OVERLAYS", {})
    monkeypatch.setattr(msp, "_local_autodetect", {})
    monkeypatch.setattr("hermes_cli.models_local.fetch_lmstudio_models", lambda **k: [])
    monkeypatch.setattr(
        "hermes_cli.models_local.fetch_ollama_local_models", lambda *a, **k: ["mistral-nemo:12b", "qwen3-vl:8b"])
    saved: list = []
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {"custom_providers": []})
    monkeypatch.setattr("hermes_cli.config.save_config", saved.append)
    return saved


def test_running_ollama_becomes_a_saved_provider_with_its_models(ollama_up):
    providers = list_authenticated_providers(
        current_provider="openrouter", current_base_url="https://openrouter.ai/api/v1", custom_providers=[])

    rows = [p for p in providers if p["name"] == "Ollama"]
    assert len(rows) == 1 and sorted(rows[0]["models"]) == ["mistral-nemo:12b", "qwen3-vl:8b"]
    assert ollama_up[0]["custom_providers"][0]["base_url"] == "http://127.0.0.1:11434/v1"


def test_already_configured_ollama_is_not_added_twice(ollama_up):
    configured = [{"name": "My Ollama", "base_url": "http://localhost:11434/v1", "models": ["llama3"]}]

    providers = list_authenticated_providers(
        current_provider="openrouter", current_base_url="https://openrouter.ai/api/v1", custom_providers=configured)

    assert [p["name"] for p in providers if "ollama" in p["name"].lower()] == ["My Ollama"]
    assert ollama_up == []
