"""Free-model rotation: a free primary falls back to the same provider's next free model, then
the next signed-in provider's free models in Providers-page order, ahead of configured fallbacks."""

import pytest

from agent import free_rotation
from hermes_cli import free_models

LISTS = {"cline": ["c/one:free"], "nous": ["n/one:free"],
         "openrouter": ["o/one:free", "o/two:free", "o/three:free"], "kilocode": ["k/one:free"], "opencode-zen": []}


@pytest.fixture
def rotation(monkeypatch):
    monkeypatch.setattr(free_models, "free_models_by_provider", lambda blocking=False: dict(LISTS))
    signed_in = {"cline", "openrouter", "kilocode"}
    monkeypatch.setattr(free_rotation, "_signed_in", lambda p: p in signed_in)
    monkeypatch.setattr(free_models, "free_mode_enabled", lambda: False)


def _pairs(chain):
    return [(e["provider"], e["model"]) for e in chain]


def test_rotates_within_provider_then_to_next_signed_in_provider(rotation):
    chain = free_rotation.free_rotation_chain("openrouter", "o/two:free")

    assert _pairs(chain) == [("openrouter", "o/three:free"), ("openrouter", "o/one:free"),
                             ("kilocode", "k/one:free"), ("cline", "c/one:free")]
    assert all(e["free_rotation"] for e in chain)


def test_paid_model_gets_no_rotation(rotation):
    assert free_rotation.free_rotation_chain("openrouter", "anthropic/claude-sonnet-5") == []


def test_rotation_goes_before_configured_fallbacks_and_is_rebuilt_on_switch(rotation):
    configured = {"provider": "anthropic", "model": "claude-haiku-5.5"}
    first = free_rotation.with_free_rotation([configured], "cline", "c/one:free")
    assert _pairs(first)[0] == ("openrouter", "o/one:free") and first[-1] == configured

    switched = free_rotation.with_free_rotation(first, "anthropic", "claude-sonnet-5")
    assert switched[0] == configured and all(e.get("on_credits_only") for e in switched[1:])


def test_switch_notice_names_provider_and_model():
    assert free_rotation.switch_notice("openrouter", "o/two:free") == "Switched to OpenRouter: o/two:free (free)"


def test_paid_model_falls_back_to_free_models_only_when_credits_run_out(rotation, monkeypatch):
    from agent.error_classifier import FailoverReason
    monkeypatch.setattr(free_models, "free_mode_enabled", lambda: False)
    configured = {"provider": "anthropic", "model": "claude-haiku-5.5"}

    chain = free_rotation.with_free_rotation([configured], "anthropic", "claude-sonnet-5")

    assert chain[0] == configured and _pairs(chain[1:3]) == [("cline", "c/one:free"), ("openrouter", "o/one:free")]
    assert free_rotation.skip_for_reason(chain[1], FailoverReason.rate_limit) is True
    assert free_rotation.skip_for_reason(chain[1], FailoverReason.billing) is False
    assert free_rotation.skip_for_reason(configured, FailoverReason.rate_limit) is False


def test_free_mode_drops_paid_fallbacks(rotation, monkeypatch):
    monkeypatch.setattr(free_models, "free_mode_enabled", lambda: True)
    configured = {"provider": "anthropic", "model": "claude-haiku-5.5"}

    chain = free_rotation.with_free_rotation([configured], "openrouter", "o/one:free")

    assert configured not in chain and all(e["free_rotation"] for e in chain)


def test_per_message_chain_refresh_keeps_free_rotation(rotation):
    """The gateway re-applies the configured chain before every message; that refresh must keep
    the free-model rotation, or a free model's first rate limit ends the turn."""
    from types import SimpleNamespace

    from gateway.run import GatewayRunner

    agent = SimpleNamespace(provider="openrouter", model="o/one:free", _fallback_chain=[], _fallback_model=None,
                            _fallback_index=0, _fallback_activated=False, _rate_limited_until=0)
    GatewayRunner._apply_fallback_chain_to_agent(agent, [])

    assert _pairs(agent._fallback_chain)[:2] == [("openrouter", "o/two:free"), ("openrouter", "o/three:free")]


def test_chain_refresh_on_an_active_fallback_keeps_the_primarys_chain(rotation):
    from types import SimpleNamespace

    from gateway.run import GatewayRunner

    agent = SimpleNamespace(provider="openrouter", model="o/two:free", _primary_runtime={"provider": "openrouter", "model": "o/one:free"},
                            _fallback_chain=[], _fallback_model=None, _fallback_index=1, _fallback_activated=True,
                            _rate_limited_until=0)
    GatewayRunner._apply_fallback_chain_to_agent(agent, [])

    assert _pairs(agent._fallback_chain)[:2] == [("openrouter", "o/two:free"), ("openrouter", "o/three:free")]
