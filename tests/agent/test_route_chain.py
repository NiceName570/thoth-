"""The fallback route chain with free-model rotation: Free mode never reaches a paid model, the
free models held for an out-of-credits failure survive earlier failures in the turn, and the
per-message refresh keeps the chain on the model it is using."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.error_classifier import FailoverReason
from hermes_cli import free_models, models_detect

LISTS = {"cline": ["c/one:free"], "nous": [], "openrouter": ["o/one:free", "o/two:free", "o/three:free"],
         "kilocode": ["k/one:free"], "opencode-zen": []}
SIGNED_IN = {"cline", "openrouter", "kilocode"}
PAID = {"provider": "anthropic", "model": "claude-haiku-5.5"}


@pytest.fixture
def lists(monkeypatch):
    current = {k: list(v) for k, v in LISTS.items()}
    monkeypatch.setattr(free_models, "free_models_by_provider", lambda blocking=False: {k: list(v) for k, v in current.items()})
    monkeypatch.setattr(models_detect, "provider_has_credentials", lambda p: p in SIGNED_IN)
    monkeypatch.setattr(free_models, "free_mode_enabled", lambda: False)
    return current


def _pairs(chain):
    return [(e["provider"], e["model"]) for e in chain]


def _refresh(agent, configured):
    from gateway.run import GatewayRunner
    GatewayRunner._apply_fallback_chain_to_agent(agent, configured)


def _gateway_agent(**fields):
    base = dict(provider="openrouter", model="o/one:free", _fallback_chain=[], _fallback_model=None,
                _fallback_index=0, _fallback_activated=False, _rate_limited_until=0)
    return SimpleNamespace(**{**base, **fields})


def test_free_mode_never_falls_back_to_paid_when_the_free_lists_fail(lists, monkeypatch):
    monkeypatch.setattr(free_models, "free_mode_enabled", lambda: True)

    def broken(blocking=False):
        raise OSError("corrupt free-model cache")
    monkeypatch.setattr(free_models, "free_models_by_provider", broken)
    agent = _gateway_agent()

    _refresh(agent, [PAID])

    assert PAID not in agent._fallback_chain


def test_refresh_during_a_fallback_continues_after_the_model_in_use(lists):
    agent = _gateway_agent(model="o/two:free", _primary_runtime={"provider": "openrouter", "model": "o/one:free"},
                           _fallback_activated=True)
    _refresh(agent, [])
    agent._fallback_index = 1  # o/two:free is in use
    assert _pairs(agent._fallback_chain)[:1] == [("openrouter", "o/two:free")]

    lists["openrouter"].insert(1, "o/new:free")  # the daily refresh adds a model ahead of it
    _refresh(agent, [])

    assert _pairs(agent._fallback_chain[agent._fallback_index:])[:1] == [("openrouter", "o/three:free")]


def _make_agent():
    from run_agent import AIAgent
    with (
        patch("model_tools.get_tool_definitions", return_value=[]),
        patch("model_tools.check_toolset_requirements", return_value={}),
        patch("agent.process_bootstrap.OpenAI"),
    ):
        agent = AIAgent(api_key="test-key", base_url="https://api.anthropic.com", provider="anthropic",
                        model="claude-sonnet-5", quiet_mode=True, skip_context_files=True, skip_memory=True)
    agent.client = MagicMock()
    return agent


def _client():
    client = MagicMock()
    client.base_url, client.api_key = "https://example.invalid/v1", "fb-key"
    return client


def test_credit_fallback_survives_an_earlier_rate_limit_in_the_turn(lists):
    agent = _make_agent()
    assert agent._fallback_chain and all(e.get("on_credits_only") for e in agent._fallback_chain)

    with patch("agent.auxiliary_client.resolve_provider_client", return_value=(_client(), "c/one:free")):
        assert agent._try_activate_fallback(reason=FailoverReason.rate_limit) is False
        assert agent._try_activate_fallback(reason=FailoverReason.billing) is True

    assert agent.provider == "cline"
