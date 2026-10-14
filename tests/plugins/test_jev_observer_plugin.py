"""Behaviour tests for the bundled jev-observer plugin (synthetic exchanges, no network).

The DefAPI call is replaced by a fake observer at ``worker._observe``; every check here is mocked.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from argparse import Namespace

PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "jev-observer"
FAKE_KEY = "test-key-not-real-0000"


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    yield hermes_home


def _load_plugin():
    if "hermes_plugins" not in sys.modules:
        ns = types.ModuleType("hermes_plugins")
        ns.__path__ = []
        sys.modules["hermes_plugins"] = ns
    for name in [m for m in sys.modules if m.startswith("hermes_plugins.jev_observer")]:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        "hermes_plugins.jev_observer", PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_plugins.jev_observer"] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeObserver:
    """Deterministic probabilities derived from the reply; can fail a set number of times."""

    def __init__(self, fail_times=0, error=None):
        self.calls = []
        self.fail_times = fail_times
        self.error = error or RuntimeError("DefAPI returned HTTP 503")

    def __call__(self, reply, turn_id, api_key):
        self.calls.append((reply, turn_id, api_key))
        if len(self.calls) <= self.fail_times:
            raise self.error
        from hermes_plugins.jev_observer.jev_adapter import ALLOWED_STATES
        base = (len(reply) % 10) / 10
        return {"turn_id": turn_id, "states": {s: base for s in sorted(ALLOWED_STATES)}, "triggers": [],
                "direction": "unknown", "evidence": [], "observer": "typesafe/jev-1.13"}


@pytest.fixture
def plugin(monkeypatch):
    mod = _load_plugin()
    observer = FakeObserver()
    monkeypatch.setattr(mod.worker, "_observe", lambda *a: observer(*a))
    monkeypatch.setattr(mod.worker, "_api_key", lambda: FAKE_KEY)
    monkeypatch.setattr(mod.worker, "_sleep", lambda s: None)
    spawned = []

    def _sync_spawn(target, *args):
        spawned.append(target.__name__)
        target(*args)
    monkeypatch.setattr(mod.worker, "spawn", _sync_spawn)
    mod.observer, mod.spawned = observer, spawned
    return mod


def _fire(mod, session, turn, user, reply, history=None):
    if history is None:
        history = [{"role": "user", "content": user}, {"role": "assistant", "content": reply}]
    mod._on_post_llm_call(session_id=session, task_id="t", turn_id=turn, user_message=user,
                          assistant_response=reply, conversation_history=history, model="claude-x", platform="cli")


def _rows(mod):
    conn = mod.store.connect()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM observations ORDER BY id")]
    finally:
        conn.close()


def test_capture_is_pending_until_background_worker_runs(monkeypatch):
    mod = _load_plugin()
    observer = FakeObserver()
    monkeypatch.setattr(mod.worker, "_observe", observer)
    monkeypatch.setattr(mod.worker, "_api_key", lambda: FAKE_KEY)
    queued = []
    monkeypatch.setattr(mod.worker, "spawn", lambda target, *args: queued.append((target, args)))

    assert _fire(mod, "s1", "turn-1", "hello", "Hi! Curious what you're building.") is None
    (row,) = _rows(mod)
    assert row["status"] == "pending" and observer.calls == []
    assert row["user_message"] == "hello" and row["assistant_reply"].startswith("Hi!")
    assert row["observer_version"] == "jev-reply-v1" and row["jev_model"] == "typesafe/jev-1.13"

    for target, args in queued:
        target(*args)
    (row,) = _rows(mod)
    probs = json.loads(row["probabilities"])
    assert row["status"] == "ok" and len(probs) == 21 and row["deltas"] is None
    assert row["observed_at"] and row["created_at"]


def test_duplicate_event_is_ignored(plugin):
    _fire(plugin, "s1", "turn-1", "hello", "Hi there.")
    _fire(plugin, "s1", "turn-1", "hello", "Hi there.")
    assert len(_rows(plugin)) == 1 and len(plugin.observer.calls) == 1


def test_deltas_between_exchanges_in_same_conversation(plugin):
    _fire(plugin, "s1", "turn-1", "a", "12345")        # 0.5
    _fire(plugin, "s1", "turn-2", "b", "1234567")      # 0.7
    _fire(plugin, "s2", "turn-3", "c", "123")          # other conversation: no basis
    r1, r2, r3 = _rows(plugin)
    deltas = json.loads(r2["deltas"])
    assert r2["delta_basis_id"] == r1["id"]
    assert set(deltas) == set(json.loads(r2["probabilities"]))
    assert all(v == pytest.approx(0.2) for v in deltas.values())
    assert r3["deltas"] is None and r3["delta_basis_id"] is None


def test_regenerated_reply_supersedes_and_preserves_earlier_record(plugin):
    _fire(plugin, "s1", "turn-1", "a", "12345")
    _fire(plugin, "s1", "turn-2", "b", "first try")
    before = _rows(plugin)[1]
    # /retry: same user text, fresh turn id, old reply no longer in history
    _fire(plugin, "s1", "turn-3", "b", "second try!")
    r1, old, new = _rows(plugin)
    assert old == before
    assert new["supersedes_id"] == old["id"] and new["exchange_key"] == old["exchange_key"]
    assert new["delta_basis_id"] == r1["id"]  # compared with the previous exchange, not the replaced reply


def test_identical_regenerated_reply_still_supersedes(plugin):
    _fire(plugin, "s1", "turn-1", "a", "12345")
    _fire(plugin, "s1", "turn-2", "b", "same words")
    history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "12345"},
               {"role": "user", "content": "b"}, {"role": "assistant", "content": "same words"}]
    _fire(plugin, "s1", "turn-3", "b", "same words", history=history)
    r1, old, new = _rows(plugin)
    assert new["supersedes_id"] == old["id"] and new["delta_basis_id"] == r1["id"]


def test_row_leased_by_another_live_process_is_left_alone(plugin, monkeypatch):
    queued = []
    monkeypatch.setattr(plugin.worker, "spawn", lambda target, *args: queued.append((target, args)))
    _fire(plugin, "s1", "turn-1", "a", "reply")
    conn = plugin.store.connect()
    conn.execute("UPDATE observations SET lease_owner='other-process', lease_at=?", (__import__("time").time(),))
    conn.commit()
    conn.close()
    plugin.worker.drain("s1")
    assert _rows(plugin)[0]["status"] == "pending" and plugin.observer.calls == []

    conn = plugin.store.connect()  # the other process died: its lease goes stale and is reclaimed
    conn.execute("UPDATE observations SET lease_at=0")
    conn.commit()
    conn.close()
    plugin.worker.drain("s1")
    assert _rows(plugin)[0]["status"] == "ok"


def test_repeated_user_text_is_a_new_exchange_when_prior_reply_remains(plugin):
    _fire(plugin, "s1", "turn-1", "continue", "part one")
    history = [{"role": "user", "content": "continue"}, {"role": "assistant", "content": "part one"},
               {"role": "user", "content": "continue"}, {"role": "assistant", "content": "part two"}]
    _fire(plugin, "s1", "turn-2", "continue", "part two", history=history)
    r1, r2 = _rows(plugin)
    assert r2["supersedes_id"] is None and r2["delta_basis_id"] == r1["id"]


def test_bounded_retries_then_success(plugin):
    plugin.observer.fail_times = 2
    _fire(plugin, "s1", "turn-1", "a", "reply")
    (row,) = _rows(plugin)
    assert row["status"] == "ok" and row["attempts"] == 3


def test_retries_exhausted_writes_redacted_error(plugin):
    plugin.observer.fail_times = 99
    plugin.observer.error = RuntimeError(f"boom with {FAKE_KEY}")
    _fire(plugin, "s1", "turn-1", "a", "reply")
    (row,) = _rows(plugin)
    assert row["status"] == "error" and row["attempts"] == 3 and len(plugin.observer.calls) == 3
    assert FAKE_KEY not in row["error"] and "[redacted]" in row["error"]


def test_missing_key_is_error_without_call(plugin, monkeypatch):
    monkeypatch.setattr(plugin.worker, "_api_key", lambda: None)
    _fire(plugin, "s1", "turn-1", "a", "reply")
    (row,) = _rows(plugin)
    assert row["status"] == "error" and "DEFAPI_API_KEY" in row["error"] and plugin.observer.calls == []


def test_hook_never_raises(plugin, monkeypatch):
    def broken(**_):
        raise OSError("disk full")
    monkeypatch.setattr(plugin.store, "insert_pending", broken)
    assert _fire(plugin, "s1", "turn-1", "a", "reply") is None


def test_restart_resumes_pending_rows(monkeypatch):
    mod = _load_plugin()
    monkeypatch.setattr(mod.worker, "spawn", lambda target, *args: None)  # process "dies" before observing
    monkeypatch.setattr(mod.worker, "_api_key", lambda: FAKE_KEY)
    _fire(mod, "s1", "turn-1", "a", "12345")
    assert _rows(mod)[0]["status"] == "pending"

    fresh = _load_plugin()  # restart
    observer = FakeObserver()
    monkeypatch.setattr(fresh.worker, "_observe", observer)
    monkeypatch.setattr(fresh.worker, "_api_key", lambda: FAKE_KEY)
    monkeypatch.setattr(fresh.worker, "spawn", lambda target, *args: target(*args))
    _fire(fresh, "s1", "turn-2", "b", "1234567")
    r1, r2 = _rows(fresh)
    assert r1["status"] == "ok" and r2["status"] == "ok" and r2["delta_basis_id"] == r1["id"]


def test_export_uses_handoff_adapter_on_latest_reply_per_exchange(plugin, tmp_path, capsys):
    from hermes_plugins.jev_observer import cli
    _fire(plugin, "s1", "turn-1", "a", "12345")
    _fire(plugin, "s1", "turn-2", "b", "first")
    _fire(plugin, "s1", "turn-3", "b", "second try!")
    out = tmp_path / "handoff.json"
    assert cli.handle(Namespace(jev_action="export", session="s1", recent=3, out=str(out))) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema"] == "jev-observer-v1"
    assert data["source_turns"] == ["turn-1", "turn-3"]
    assert data["direction"] == "unknown" and data["recent_triggers"] == []
    assert data["observer_version"] == "jev-reply-v1" and data["conversation_id"] == "s1"

    capsys.readouterr()
    cli.handle(Namespace(jev_action="export", session="s1", recent=1, out=None))
    assert json.loads(capsys.readouterr().out)["source_turns"] == ["turn-3"]


def test_bundled_plugin_is_opt_in(_isolate_env):
    from hermes_cli import plugins as pmod
    mgr = pmod.PluginManager()
    mgr.discover_and_load()
    loaded = mgr._plugins["jev-observer"]
    assert loaded.manifest.source == "bundled" and not loaded.enabled


def test_enabled_plugin_registers_hook_and_cli(_isolate_env):
    import hermes_yaml as yaml
    (_isolate_env / "config.yaml").write_text(yaml.safe_dump({"plugins": {"enabled": ["jev-observer"]}}))
    from hermes_cli import plugins as pmod
    mgr = pmod.PluginManager()
    mgr.discover_and_load()
    assert mgr._plugins["jev-observer"].enabled
    assert mgr._hooks.get("post_llm_call")
    assert "jev-observer" in mgr._cli_commands
