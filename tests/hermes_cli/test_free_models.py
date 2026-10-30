"""Free daily models in the model picker: free models are listed and marked free, and an account
with no credits sees only its free models; one that can't report credits keeps everything."""

import json
import time

import pytest

from hermes_cli import free_models


@pytest.fixture
def free_lists(monkeypatch, tmp_path):
    path = tmp_path / "free_models.json"
    monkeypatch.setattr(free_models, "_cache_path", lambda: path)
    monkeypatch.setattr(free_models, "ensure_daily_refresh", lambda: None)
    path.write_text(json.dumps({"fetched_at": time.time(), "providers": {
        "openrouter": ["a/one:free", "b/two:free"], "cline": ["c/three:free"]}, "levels": {}}))
    return path


def _row(slug, models):
    return {"slug": slug, "models": list(models), "total_models": len(models), "pricing": {}}


def test_no_credits_lists_only_free_models(free_lists, monkeypatch):
    monkeypatch.setattr(free_models, "free_mode_enabled", lambda: False)
    monkeypatch.setattr(free_models, "credit_state", lambda slug: free_models.CREDITS_NONE)
    row = _row("openrouter", ["paid/model", "a/one:free"])

    free_models.decorate_picker_rows([row])

    assert row["models"] == ["a/one:free", "b/two:free"]
    assert row["pricing"]["b/two:free"]["free"] is True
    assert row["warning"] == free_models.NO_CREDITS_WARNING


def test_unknown_credits_keeps_every_model_and_marks_free(free_lists, monkeypatch):
    monkeypatch.setattr(free_models, "free_mode_enabled", lambda: False)
    monkeypatch.setattr(free_models, "credit_state", lambda slug: free_models.CREDITS_UNKNOWN)
    row = _row("cline", ["cline-pass/glm-5.3"])

    free_models.decorate_picker_rows([row])

    assert row["models"] == ["cline-pass/glm-5.3", "c/three:free"]
    assert row["pricing"]["c/three:free"]["free"] is True
    assert row["featured_models"] == ["c/three:free"]
    assert "cline-pass/glm-5.3" not in row["pricing"]


def test_stale_list_refreshes_in_background_without_blocking(free_lists, monkeypatch):
    free_lists.write_text(json.dumps({"fetched_at": 0, "providers": {"openrouter": ["a/one:free"]}}))
    started = []
    monkeypatch.setattr(free_models, "_refresh_in_background", lambda: started.append(True))

    assert free_models.free_models("openrouter") == ["a/one:free"]
    assert started == [True]


def test_failed_catalog_read_keeps_the_last_list(free_lists, monkeypatch):
    monkeypatch.setitem(free_models._FETCHERS, "openrouter", dict)
    monkeypatch.setitem(free_models._FETCHERS, "cline", lambda: {"c/new:free": None})

    lists = free_models.refresh_free_models(("openrouter", "cline"))

    assert lists["openrouter"] == ["a/one:free", "b/two:free"]
    assert lists["cline"] == ["c/new:free"]


def test_free_mode_lists_only_free_models_and_drops_local_endpoints(free_lists, monkeypatch):
    monkeypatch.setattr(free_models, "free_mode_enabled", lambda: True)
    monkeypatch.setattr(free_models, "credit_state", lambda slug: free_models.CREDITS_AVAILABLE)
    rows = [_row("openrouter", ["paid/model", "a/one:free"]), _row("anthropic", ["claude-sonnet-5"]),
            _row("custom:ollama", ["qwen3:14b"])]

    free_models.decorate_picker_rows(rows)

    assert [r["slug"] for r in rows] == ["openrouter"]
    assert rows[0]["models"] == ["a/one:free", "b/two:free"] and "warning" not in rows[0]


def test_refresh_that_reaches_no_provider_retries_soon(free_lists, monkeypatch):
    for slug in free_models.FREE_MODEL_PROVIDERS:
        monkeypatch.setitem(free_models._FETCHERS, slug, dict)

    free_models.refresh_free_models()

    fetched_at = json.loads(free_lists.read_text())["fetched_at"]
    assert time.time() - fetched_at > free_models.REFRESH_SECONDS - 16 * 60


def test_refresh_records_each_models_top_reasoning_level(free_lists, monkeypatch):
    """Levels come from the provider's own catalog; a catalog that publishes none (Cline) borrows
    OpenRouter's for the same model id."""
    catalogs = {
        "https://openrouter.ai/api/v1/models": {"data": [
            {"id": "a/one:free", "supported_parameters": ["reasoning"],
             "reasoning": {"supported_efforts": ["high", "medium", "low"]}},
            {"id": "b/two:free", "supported_parameters": ["tools"]},
            {"id": "c/three:free", "supported_parameters": ["reasoning"]}]},
        "https://api.cline.bot/api/v1/models": {"data": [{"id": "a/one:free"}]},
        "https://opencode.ai/zen/v1/models": {"data": [
            {"id": "z-free", "capabilities": {"reasoning": {"supported": True, "effort": ["low", "max"]}}}]},
    }
    monkeypatch.setattr(free_models, "_get_json", lambda url, headers=None: catalogs.get(url))

    free_models.refresh_free_models(("openrouter", "cline", "opencode-zen"))

    assert free_models.free_model_levels() == {
        "openrouter": {"a/one:free": "high", "b/two:free": "off", "c/three:free": "reasoning"},
        "cline": {"a/one:free": "high"}, "opencode-zen": {"z-free": "max"}}


def test_free_mode_starts_on_the_strongest_reasoner(free_lists, monkeypatch):
    from hermes_cli import models_detect
    free_lists.write_text(json.dumps({"fetched_at": time.time(),
        "providers": {"cline": ["c/three:free"], "openrouter": ["a/one:free", "b/two:free"]},
        "levels": {"cline": {"c/three:free": "medium"}, "openrouter": {"b/two:free": "max"}}}))
    monkeypatch.setattr(models_detect, "provider_has_credentials", lambda p: True)

    assert free_models.first_free_model() == ("openrouter", "b/two:free")


def test_cache_without_reasoning_levels_refreshes_now(free_lists, monkeypatch):
    free_lists.write_text(json.dumps({"fetched_at": time.time(), "providers": {"openrouter": ["a/one:free", "b/two:free"]}}))
    started = []
    monkeypatch.setattr(free_models, "_refresh_in_background", lambda: started.append(True))

    assert free_models.free_models("openrouter") == ["a/one:free", "b/two:free"]
    assert started == [True]
