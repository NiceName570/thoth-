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
        "openrouter": ["a/one:free", "b/two:free"], "cline": ["c/three:free"]}}))
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
    monkeypatch.setitem(free_models._FETCHERS, "openrouter", list)
    monkeypatch.setitem(free_models._FETCHERS, "cline", lambda: ["c/new:free"])

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
