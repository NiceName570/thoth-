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
    assert switched == [configured]


def test_switch_notice_names_provider_and_model():
    assert free_rotation.switch_notice("openrouter", "o/two:free") == "Switched to OpenRouter: o/two:free (free)"
