"""Free mode, end to end against a temp HERMES_HOME: turning it on moves the main model to the
first signed-in free model and remembers the old one; turning it off puts the old one back."""

import pytest

from hermes_cli import free_models


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "model:\n  provider: anthropic\n  default: claude-sonnet-5\n", encoding="utf-8")
    monkeypatch.setattr(free_models, "first_free_model", lambda: ("openrouter", "o/one:free"))
    from hermes_cli.web_routers import models as route

    def _assign(scope, provider, model, task, base_url, api_key="", **_):
        from hermes_cli.config import load_config, save_config
        cfg = load_config()
        cfg["model"] = {**cfg.get("model", {}), "provider": provider, "default": model}
        save_config(cfg)

    monkeypatch.setattr(route, "_apply_model_assignment_sync", _assign)
    monkeypatch.setattr(route, "_prepare_main_assignment", lambda *a: None)
    return route


def _toggle(route, enabled):
    import asyncio

    from hermes_cli.web_models import FreeModeToggle
    return asyncio.run(route.set_free_mode(FreeModeToggle(enabled=enabled)))


def test_free_mode_round_trip_restores_the_chosen_model(home):
    on = _toggle(home, True)
    assert on == {"enabled": True, "provider": "openrouter", "model": "o/one:free"}
    assert free_models.free_mode_enabled() is True
    # Turning it on again keeps the model chosen before Free mode, not the free one.
    _toggle(home, True)

    off = _toggle(home, False)
    assert off == {"enabled": False, "provider": "anthropic", "model": "claude-sonnet-5"}
    assert free_models.free_mode_enabled() is False


def test_free_mode_needs_a_provider_with_free_models(home, monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(free_models, "first_free_model", lambda: None)

    with pytest.raises(HTTPException) as err:
        _toggle(home, True)
    assert err.value.status_code == 409 and free_models.free_mode_enabled() is False
