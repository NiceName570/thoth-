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
    monkeypatch.setattr(free_models, "free_model_levels", dict)
    monkeypatch.setattr(models_detect, "provider_has_credentials", lambda p: p in SIGNED_IN)
    monkeypatch.setattr(free_models, "free_mode_enabled", lambda: False)
    return current


def _pairs(chain):
    return [(e["provider"], e["model"]) for e in chain]


def test_free_model_rotates_within_its_provider_then_to_the_next_signed_in_one(lists):
    from agent.route_chain import build_chain

    chain = build_chain([PAID], "openrouter", "o/two:free")

    assert _pairs(chain) == [("openrouter", "o/three:free"), ("openrouter", "o/one:free"),
                             ("kilocode", "k/one:free"), ("cline", "c/one:free"), (PAID["provider"], PAID["model"])]
    assert all(e["free_rotation"] for e in chain[:-1])


def test_rotation_tries_the_strongest_reasoners_first(lists, monkeypatch):
    """Highest published reasoning level first (max, then high, then medium), then reasoning
    models with no published levels, then low-only, then models that don't reason; ties keep the
    provider-by-provider order."""
    from agent.route_chain import build_chain
    monkeypatch.setattr(free_models, "free_model_levels", lambda: {
        "openrouter": {"o/one:free": "medium", "o/three:free": "off"},
        "kilocode": {"k/one:free": "max"}, "cline": {"c/one:free": "high"}})

    rotation = build_chain([], "openrouter", "o/two:free")
    credits = build_chain([], "anthropic", "claude-sonnet-5")

    assert _pairs(rotation) == [("kilocode", "k/one:free"), ("cline", "c/one:free"),
                                ("openrouter", "o/one:free"), ("openrouter", "o/three:free")]
    assert _pairs(credits)[:3] == [("kilocode", "k/one:free"), ("cline", "c/one:free"), ("openrouter", "o/one:free")]


def test_paid_model_keeps_its_fallbacks_and_holds_free_models_for_credits(lists):
    from agent.route_chain import build_chain, configured_entries

    free_first = build_chain([PAID], "cline", "c/one:free")
    switched = build_chain(free_first, "anthropic", "claude-sonnet-5")

    assert switched[0] == PAID and all(e.get("on_credits_only") for e in switched[1:])
    assert configured_entries(switched) == [PAID]


def test_free_mode_drops_paid_fallbacks(lists, monkeypatch):
    from agent.route_chain import build_chain
    monkeypatch.setattr(free_models, "free_mode_enabled", lambda: True)

    chain = build_chain([PAID], "openrouter", "o/one:free")

    assert PAID not in chain and all(e["free_rotation"] for e in chain)


def test_switch_notice_for_free_and_configured_entries():
    from agent.route_chain import switch_notice

    free = switch_notice({"free_rotation": True}, "openrouter", "o/two:free",
                         old_provider="openrouter", old_model="o/one:free", reason_text="rate limit", retry_in=60)
    paid = switch_notice(PAID, "anthropic", "claude-haiku-5.5", old_provider="openai", old_model="gpt-5",
                         reason_text="rate limit", retry_in=60)

    assert free == "Switched to OpenRouter: o/two:free (free)"
    assert paid.startswith("⚠️ Model fallback: gpt-5 via openai unavailable (rate limit)") and "~60 s" in paid


def _refresh(agent, configured):
    from gateway.run import GatewayRunner
    GatewayRunner._apply_fallback_chain_to_agent(agent, configured)


def _gateway_agent(**fields):
    base = dict(provider="openrouter", model="o/one:free", _fallback_chain=[], _fallback_model=None,
                _fallback_index=0, _fallback_activated=False, _rate_limited_until=0)
    return SimpleNamespace(**{**base, **fields})


def test_per_message_refresh_builds_the_chain_around_the_primary(lists):
    """The gateway re-applies the configured chain before every message: it must keep the free
    rotation, built around the primary rather than an active fallback."""
    idle = _gateway_agent()
    _refresh(idle, [])
    active = _gateway_agent(model="o/two:free", _primary_runtime={"provider": "openrouter", "model": "o/one:free"},
                            _fallback_activated=True)
    _refresh(active, [])

    expected = [("openrouter", "o/two:free"), ("openrouter", "o/three:free")]
    assert _pairs(idle._fallback_chain)[:2] == expected and idle._fallback_index == 0
    assert _pairs(active._fallback_chain)[:2] == expected


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
