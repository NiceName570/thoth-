"""A running LM Studio shows up in the model picker with no setup, and a closed port is probed at most
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
    monkeypatch.setattr(msp, "_lmstudio_autodetect", {})
    calls: list[str] = []
    catalog: list[str] = []

    def _fake_fetch(api_key=None, base_url=None, timeout=5.0):
        calls.append(base_url)
        return list(catalog)

    monkeypatch.setattr("hermes_cli.models_local.fetch_lmstudio_models", _fake_fetch)
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
