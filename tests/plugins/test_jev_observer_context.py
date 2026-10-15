"""Contextual jev-observer (jev-context-v1) plumbing, with a scripted fake Jev.

Every check here is mocked: the fake decides answers from scripted scenarios, so these tests
prove context assembly, evidence validation, movement, patterns and persistence, not that Jev
judges well. Live judgment quality is checked separately.
"""

import importlib.util
import json
import sys
import types
from argparse import Namespace
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "jev-observer"
PROVIDER = {"name": "defapi", "key": "DEFAPI_API_KEY", "endpoint": "https://example.invalid", "model": "typesafe/jev-1.13"}
KEY = "test-key-not-real-1111"


def _config(home: Path, **settings) -> None:
    body = "".join(f"        {k}: {str(v).lower() if isinstance(v, bool) else v}\n" for k, v in settings.items())
    (home / "config.yaml").write_text(
        "plugins:\n  entries:\n    jev-observer:\n      settings:\n" + (body or "        {}\n"), encoding="utf-8")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    h = tmp_path / ".hermes"
    h.mkdir()
    _config(h)
    monkeypatch.setenv("HERMES_HOME", str(h))
    return h


def _load():
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


class FakeJev:
    """Scripted answers keyed by a marker in the T0 user message; neutral defaults otherwise.

    ``script[marker][judgment] = result``; ``evidence[marker][judgment] = substring`` picks the
    first span containing it."""

    def __init__(self, script=None, evidence=None, fail_times=0):
        self.script, self.evidence, self.fail_times = script or {}, evidence or {}, fail_times
        self.calls = []

    def __call__(self, state, questions, provider, key):
        from hermes_plugins.jev_observer import rubric
        self.calls.append((state, questions))
        if len(self.calls) <= self.fail_times:
            raise RuntimeError(f"HTTP 503 with {key}")
        user = state["current"]["user"]
        marker = next((m for m in self.script if m in user), None)
        scripted = self.script.get(marker, {})
        ev = self.evidence.get(marker, {})
        answers = {}
        for j in rubric.JUDGMENTS:
            value = scripted.get(j["id"])
            if j["type"] == "noul":
                answers[j["id"]] = {"type": "noul", "noul": 0.1 if value is None else value}
            elif j["type"] == "score":
                s = 2.0 if value is None else value
                answers[j["id"]] = {"type": "score", "score": s, "legend": {}, "probabilities": {"2": 1.0},
                                    "confidence": 0.9}
            else:
                choice = value or next(iter(j["criteria"]))
                answers[j["id"]] = {"type": "choice", "choice": choice, "probabilities": {choice: 0.9},
                                    "confidence": 0.9}
            qid = rubric.evidence_qid(j["id"])
            if qid in questions:
                want = ev.get(j["id"])
                pick = next((sid for sid, text in questions[qid]["criteria"].items()
                             if want and sid != "none" and want in text), "none")
                answers[qid] = {"type": "choice", "choice": pick, "probabilities": {pick: 1.0}, "confidence": 0.8}
        return {"answers": answers, "usage": {"input_tokens": 100, "output_tokens": 10, "cost": 1e-05},
                "model": "typesafe/jev-1.13-test", "latency_ms": 42}


@pytest.fixture
def obs(monkeypatch):
    mod = _load()
    jev = FakeJev()
    monkeypatch.setattr(mod.worker, "_resolve", lambda: (PROVIDER, KEY))
    monkeypatch.setattr(mod.worker, "_sleep", lambda s: None)
    monkeypatch.setattr(mod.worker, "_observe", lambda reply, turn_id, provider, key: {
        "turn_id": turn_id, "states": {"warmth": 0.9}, "triggers": [], "direction": "unknown", "evidence": []})
    monkeypatch.setattr(mod.worker, "spawn", lambda target, *args: target(*args))
    from hermes_plugins.jev_observer import context_worker
    monkeypatch.setattr(context_worker, "_decide", lambda *a: jev(*a))
    mod.jev = jev
    return mod


def _history(exchanges):
    msgs = []
    for u, a in exchanges:
        msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    return msgs


def _converse(mod, session, exchanges, start=1):
    for i, (user, reply) in enumerate(exchanges, start):
        mod._on_post_llm_call(session_id=session, turn_id=f"turn-{i}", user_message=user, assistant_response=reply,
                              conversation_history=_history(exchanges[:i - start + 1]), model="m", platform="cli")


def _ctx_rows(mod):
    conn = mod.context_store.connect()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT c.*, o.turn_id FROM context_observations c JOIN observations o ON o.id=c.capture_id ORDER BY c.id")]
    finally:
        conn.close()
    for r in rows:
        for k in ("judgments", "movement", "patterns", "context", "usage"):
            r[k] = json.loads(r[k]) if r[k] else None
    return rows


def _baseline_rows(mod):
    conn = mod.store.connect()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM observations ORDER BY id")]
    finally:
        conn.close()


# ── plumbing ────────────────────────────────────────────────────────────────

def test_exchange_gets_a_separate_contextual_row_with_full_record(obs):
    _converse(obs, "s1", [("Can you check the schema?", "Sure. The schema has three tables.")])
    (base,) = _baseline_rows(obs)
    (row,) = _ctx_rows(obs)
    assert base["observer_version"] == "jev-reply-v1" and base["status"] == "ok"
    assert row["status"] == "ok" and row["capture_id"] == base["id"]
    assert (row["observer_version"], row["rubric_version"], row["run"]) == ("jev-context-v1", "ctx-rubric-1", "live")
    from hermes_plugins.jev_observer import rubric
    assert set(row["judgments"]) == set(rubric.BY_ID)
    for jid, j in row["judgments"].items():
        assert j["target"] in ("assistant", "user", "interaction") and j["definition"]
    assert row["latency_ms"] == 42 and row["usage"]["input_tokens"] == 100
    assert row["jev_model"] == "defapi:typesafe/jev-1.13-test"
    assert row["context"]["window_turn_ids"] == [] and row["context"]["capture_turn_id"] == "turn-1"


def test_context_window_is_bounded_and_labelled(obs, home):
    _config(home, context_window=2)
    _converse(obs, "s1", [(f"question {i}.", f"answer {i}.") for i in range(1, 5)])
    last = _ctx_rows(obs)[-1]
    assert last["context"]["window_turn_ids"] == ["turn-2", "turn-3"]
    state = obs.jev.calls[-1][0]
    assert [t["label"] for t in state["window"]] == ["T-2", "T-1"] and state["current"]["user"] == "question 4."


def test_evidence_is_quoted_exactly_and_traced_to_its_turn(obs):
    obs.jev.script = {"schema": {"understanding": "substituted_claim"}}
    obs.jev.evidence = {"schema": {"understanding": "REST API"}}
    _converse(obs, "s1", [("No, I meant the database schema.", "Great question! Here is how the REST API works.")])
    j = _ctx_rows(obs)[0]["judgments"]["understanding"]
    (ev,) = j["evidence"]
    assert ev["turn_id"] == "turn-1" and ev["role"] == "assistant" and ev["text"] == "Here is how the REST API works."


def test_spans_keep_code_and_numbers_whole():
    _load()
    from hermes_plugins.jev_observer import context
    text = "Lists are mutable: a.append(2) works. Pi is 3.14!\nNext line"
    assert context.split_spans(text) == ["Lists are mutable: a.append(2) works.", "Pi is 3.14!", "Next line"]
    assert all(s in text for s in context.split_spans(text))


def test_evidence_not_in_the_captured_source_is_dropped(obs):
    from hermes_plugins.jev_observer import context
    spans = {"S1": {"id": "S1", "label": "T0", "turn_id": "t", "role": "user", "text": "never said this"}}
    assert context.resolve_evidence("S1", spans, {"t:user": "something else entirely"}) == []
    assert context.resolve_evidence("S9", spans, {"t:user": "never said this"}) == []


def test_friendly_wording_and_misunderstanding_are_recorded_independently(obs):
    obs.jev.script = {"schema": {"understanding": "substituted_claim", "warmth": 0.95, "relationship": "misunderstanding"}}
    _converse(obs, "s1", [("No, I meant the database schema.", "Great question! Happy to help with the API!")])
    j = _ctx_rows(obs)[0]["judgments"]
    assert j["understanding"]["result"] == "substituted_claim" and j["warmth"]["result"] == 0.95
    assert j["relationship"]["result"] == "misunderstanding"


def test_insufficient_evidence_is_kept_and_never_counted_as_change(obs):
    obs.jev.script = {"first": {"understanding": "addressed_meaning"}, "second": {"understanding": "insufficient_evidence"}}
    _converse(obs, "s1", [("first point.", "ok."), ("second point.", "hmm.")])
    second = _ctx_rows(obs)[1]
    assert second["judgments"]["understanding"]["status"] == "insufficient_evidence"
    assert "understanding" not in second["movement"]["changes"]


def test_movement_names_its_comparison_basis(obs):
    obs.jev.script = {"first": {"stance": "resisting", "engagement": 1.0}, "second": {"stance": "conceding", "engagement": 3.0}}
    _converse(obs, "s1", [("first point.", "No."), ("second point.", "Fair, you are right.")])
    first, second = _ctx_rows(obs)
    m = second["movement"]
    assert m["basis"] == {"row_id": first["id"], "turn_id": "turn-1"}
    assert m["changes"]["stance"] == {"from": "resisting", "to": "conceding"}
    assert m["changes"]["engagement"]["delta"] == 2.0


def test_apology_then_same_mistake_is_a_pattern(obs):
    obs.jev.script = {
        "wrong again": {"correction_present": 0.95, "correction_uptake": "acknowledged_only"},
        "Still wrong": {"correction_present": 0.95, "correction_uptake": "acknowledged_only",
                        "repeats_corrected_mistake": 0.9},
    }
    _converse(obs, "s1", [("Use tabs.", "Here it is with spaces."), ("That's wrong again, tabs.", "Sorry! Spaces:"),
                          ("Still wrong. Tabs!", "Apologies, here it is with spaces.")])
    patterns = {p["pattern"]: p for p in _ctx_rows(obs)[-1]["patterns"]}
    assert patterns["acknowledgment_without_change"]["turn_ids"] == ["turn-2", "turn-3"]
    assert "turn-3" in patterns["mistake_repeated_after_correction"]["turn_ids"]


def test_correction_that_sticks_is_a_sustained_correction(obs):
    obs.jev.script = {
        "fix": {"correction_present": 0.9, "correction_uptake": "changed_and_acknowledged"},
        "next": {"correction_persistence": "maintained"},
    }
    _converse(obs, "s1", [("Draft it.", "Draft A."), ("fix: use metric.", "Updated to metric."),
                          ("next one.", "Metric draft B."), ("next again.", "Metric draft C.")])
    patterns = {p["pattern"]: p for p in _ctx_rows(obs)[-1]["patterns"]}
    assert patterns["sustained_correction"]["turn_ids"] == ["turn-2", "turn-3", "turn-4"]


def test_earlier_corrections_outside_the_window_are_carried_with_their_turn(obs, home):
    _config(home, context_window=1, open_corrections=2)
    obs.jev.script = {"metric": {"correction_present": 0.9}}
    _converse(obs, "s1", [("Draft it.", "Draft."), ("Use metric units.", "Metric draft."),
                          ("more.", "More."), ("and more.", "Even more.")])
    last = _ctx_rows(obs)[-1]
    assert last["context"]["correction_turn_ids"] == ["turn-2"]
    state = obs.jev.calls[-1][0]
    assert state["earlier_corrections"] == [{"label": "C1", "user": "Use metric units."}]


def test_duplicate_event_creates_one_contextual_row(obs):
    _converse(obs, "s1", [("hello.", "hi.")])
    _converse(obs, "s1", [("hello.", "hi.")])
    assert len(_ctx_rows(obs)) == 1 and len(obs.jev.calls) == 1


def test_regenerated_reply_gets_its_own_row_and_leaves_the_old_one(obs):
    _converse(obs, "s1", [("one.", "first."), ("two.", "bad reply.")])
    before = _ctx_rows(obs)[1]
    obs._on_post_llm_call(session_id="s1", turn_id="turn-3", user_message="two.", assistant_response="better reply.",
                          conversation_history=_history([("one.", "first."), ("two.", "better reply.")]),
                          model="m", platform="cli")
    rows = _ctx_rows(obs)
    assert rows[1] == before and len(rows) == 3
    assert rows[2]["context"]["window_turn_ids"] == ["turn-1"]  # the replaced reply is not context
    assert rows[2]["basis_id"] == rows[0]["id"]


def test_restart_resumes_pending_contextual_rows(monkeypatch):
    dead = _load()
    monkeypatch.setattr(dead.worker, "spawn", lambda target, *args: None)
    dead._on_post_llm_call(session_id="s1", turn_id="turn-1", user_message="hi.", assistant_response="hello.",
                           conversation_history=[], model="m", platform="cli")
    assert _ctx_rows(dead)[0]["status"] == "pending"
    fresh = _load()
    jev = FakeJev()
    monkeypatch.setattr(fresh.worker, "_resolve", lambda: (PROVIDER, KEY))
    monkeypatch.setattr(fresh.worker, "_observe", lambda *a: {"turn_id": "x", "states": {}, "triggers": []})
    monkeypatch.setattr(fresh.worker, "spawn", lambda target, *args: target(*args))
    from hermes_plugins.jev_observer import context_worker
    monkeypatch.setattr(context_worker, "_decide", jev)
    fresh.worker.requeue_all()
    assert _ctx_rows(fresh)[0]["status"] == "ok"


def test_contextual_failure_never_blocks_the_baseline(obs, monkeypatch):
    from hermes_plugins.jev_observer import context_store
    monkeypatch.setattr(context_store, "insert_pending", lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))
    _converse(obs, "s1", [("hi.", "hello.")])
    assert _baseline_rows(obs)[0]["status"] == "ok" and _ctx_rows(obs) == []


def test_assembly_failure_settles_as_error_and_unblocks_the_queue(obs, monkeypatch):
    from hermes_plugins.jev_observer import context_store
    real = context_store.capture_row
    calls = []

    def flaky(capture_id):
        calls.append(capture_id)
        if len(calls) == 1:
            raise ValueError("corrupt row")
        return real(capture_id)
    monkeypatch.setattr(context_store, "capture_row", flaky)
    _converse(obs, "s1", [("one.", "a."), ("two.", "b.")])
    first, second = _ctx_rows(obs)
    assert first["status"] == "error" and "context assembly failed" in first["error"]
    assert second["status"] == "ok"


def test_rows_queued_under_another_rubric_are_not_judged_with_this_one(obs):
    from hermes_plugins.jev_observer import context_store
    obs.worker.spawn = lambda target, *args: None
    _converse(obs, "s1", [("hi.", "hello.")])
    conn = context_store.connect()
    conn.execute("UPDATE context_observations SET rubric_version='ctx-rubric-0'")
    conn.commit()
    conn.close()
    obs.worker.drain("s1")
    (row,) = _ctx_rows(obs)
    assert row["status"] == "error" and "ctx-rubric-0" in row["error"] and obs.jev.calls == []


def test_changed_context_settings_start_a_fresh_comparison(obs, home):
    _converse(obs, "s1", [("one.", "a.")])
    _config(home, context_window=0)
    _converse(obs, "s1", [("two.", "b.")], start=2)
    assert _ctx_rows(obs)[1]["basis_id"] is None


def test_regenerated_correction_is_not_repeated_as_an_earlier_correction(obs, home):
    _config(home, context_window=2, open_corrections=3)
    obs.jev.script = {"metric": {"correction_present": 0.9}}
    _converse(obs, "s1", [("Draft it.", "Draft."), ("Use metric units.", "Metric draft.")])
    obs.worker.spawn = lambda target, *args: None  # the regenerated reply is captured but not yet judged
    obs._on_post_llm_call(session_id="s1", turn_id="turn-3", user_message="Use metric units.",
                          assistant_response="Metric draft v2.", conversation_history=_history(
                              [("Draft it.", "Draft."), ("Use metric units.", "Metric draft v2.")]), model="m", platform="cli")
    obs.worker.spawn = lambda target, *args: target(*args)
    _converse(obs, "s1", [("more.", "More.")], start=4)
    last = _ctx_rows(obs)[-1]
    assert "turn-3" in last["context"]["window_turn_ids"] and last["context"]["correction_turn_ids"] == []


def test_out_of_range_scores_and_confidences_are_rejected():
    _load()
    from hermes_plugins.jev_observer import rubric
    j = rubric.BY_ID["momentum"]
    with pytest.raises(ValueError):
        rubric.parse_answer(j, {"type": "score", "score": 7, "probabilities": {"4": 1.0}, "confidence": 0.9})
    with pytest.raises(ValueError):
        rubric.parse_answer(rubric.BY_ID["stance"], {"type": "choice", "choice": "direct",
                                                     "probabilities": {"direct": 1.0}, "confidence": 1.5})


def test_user_targeted_judgments_only_cite_user_words(obs):
    obs.jev.script = {"wrong": {"user_friction": 0.9}}
    obs.jev.evidence = {"wrong": {"user_friction": "Sorry"}}  # an assistant sentence
    _converse(obs, "s1", [("That's wrong.", "Sorry about that.")])
    assert _ctx_rows(obs)[0]["judgments"]["user_friction"]["evidence"] == []


def test_malformed_answers_end_as_an_explicit_redacted_error(obs, monkeypatch):
    from hermes_plugins.jev_observer import context_worker
    monkeypatch.setattr(context_worker, "_decide", lambda *a: {"answers": {}, "usage": {}, "model": "m", "latency_ms": 1})
    _converse(obs, "s1", [("hi.", "hello.")])
    (row,) = _ctx_rows(obs)
    assert row["status"] == "error" and row["attempts"] == 3 and "missing or mistyped" in row["error"]
    assert row["context"]["capture_turn_id"] == "turn-1"


def test_failures_retry_and_never_leak_the_key(obs):
    obs.jev.fail_times = 99
    _converse(obs, "s1", [("hi.", "hello.")])
    (row,) = _ctx_rows(obs)
    assert row["status"] == "error" and KEY not in row["error"]


def test_contextual_setting_off_records_baseline_only(obs, home):
    _config(home, contextual=False)
    _converse(obs, "s1", [("hi.", "hello.")])
    assert len(_baseline_rows(obs)) == 1 and _ctx_rows(obs) == []


def test_baseline_rows_are_untouched_by_contextual_processing(obs, home):
    _config(home, contextual=False)
    _converse(obs, "s1", [("hi.", "hello."), ("more.", "sure.")])
    before = _baseline_rows(obs)
    from hermes_plugins.jev_observer import context_report
    run, _ = context_report.rescore("s1")
    obs.worker.drain("s1")  # the passive drain leaves an explicit rescore alone
    assert {r["status"] for r in _ctx_rows(obs)} == {"pending"}
    obs.worker.drain_run("s1", run)
    assert _baseline_rows(obs) == before and len(_ctx_rows(obs)) == 2


def test_rescore_is_explicit_and_keeps_earlier_runs(obs, capsys):
    from hermes_plugins.jev_observer import cli
    _converse(obs, "s1", [("one.", "a."), ("two.", "b.")])
    live = _ctx_rows(obs)
    assert cli.handle(Namespace(jev_action="rescore", session="s1", limit=None)) == 0
    rows = _ctx_rows(obs)
    assert rows[:2] == live and len(rows) == 4
    assert {r["run"] for r in rows[2:]} == {rows[2]["run"]} and rows[2]["run"].startswith("rescore-")
    assert rows[3]["basis_id"] == rows[2]["id"]  # compared within its own run only


def test_timeline_and_handoff_export(obs, tmp_path, capsys):
    from hermes_plugins.jev_observer import cli
    obs.jev.script = {"schema": {"understanding": "substituted_claim", "correction_present": 0.9}}
    obs.jev.evidence = {"schema": {"understanding": "REST API"}}
    _converse(obs, "s1", [("Show me the tables.", "Here they are."),
                          ("No, the schema please.", "Sure! The REST API has endpoints.")])
    assert cli.handle(Namespace(jev_action="timeline", session="s1", run=None, json=False, out=None)) == 0
    text = capsys.readouterr().out
    assert "turn turn-2" in text and "understanding (assistant): substituted claim" in text
    assert '"The REST API has endpoints."' in text and "[was addressed meaning at turn turn-1]" in text
    out = tmp_path / "h.json"
    cli.handle(Namespace(jev_action="export", session="s1", recent=3, out=str(out), observer="context", run=None))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema"] == "jev-context-handoff-v1" and data["source_turns"] == ["turn-1", "turn-2"]
    assert data["latest"]["understanding"]["evidence"]["text"] == "The REST API has endpoints."
    assert data["changes"][0]["basis_turn_id"] == "turn-1"
    cli.handle(Namespace(jev_action="timeline", session="s1", run=None, json=True, out=str(out)))
    assert len(json.loads(out.read_text(encoding="utf-8"))["turns"]) == 2


def test_settings_render_on_the_plugins_page(home):
    from hermes_cli.plugins_settings import plugin_settings_fields
    fields = {f["key"]: f for f in plugin_settings_fields("jev-observer", PLUGIN_DIR)}
    assert fields["contextual"]["type"] == "boolean" and fields["contextual"]["value"] is True
    assert fields["context_window"]["value"] == 4
