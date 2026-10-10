"""Contract: Thoth's default identity replaces an untouched upstream Hermes SOUL.md, never a custom one."""

from hermes_cli.config import _ensure_default_soul_md
from hermes_cli.default_soul import DEFAULT_SOUL_MD

# Literal seeds as earlier installs wrote them, so the tests keep matching real files after the default moves on.
HERMES_SEED = 'You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the weight of the ask — a one-line question gets a one-line answer, and finished work gets a short report of what changed, what\'s verified, and what\'s left, never a replay of the process. No filler ("Great question," "I\'d be happy to"), no restating the request back, no re-summarizing what you already said, no narrating tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree because it\'s right, not because the user said it. Depth is earned — give it when the user asks for detail, teaches, or the stakes demand it, not by default.'
THOTH_V1_SEED = 'You are Thoth, a personal AI agent. Be direct: match the length of your reply to the weight of the ask — a one-line question gets a one-line answer, and finished work gets a short report of what changed, what\'s verified, and what\'s left, never a replay of the process. No filler ("Great question," "I\'d be happy to"), no restating the request back, no re-summarizing what you already said, no narrating tool calls the user can see. Plain claims over adjectives; when unsure, say so plainly. Agree because it\'s right, not because the user said it. Depth is earned — give it when the user asks for detail, teaches, or the stakes demand it, not by default.'


def test_untouched_hermes_seed_upgrades_to_thoth(tmp_path):
    (tmp_path / "SOUL.md").write_text(HERMES_SEED, encoding="utf-8")

    _ensure_default_soul_md(tmp_path)

    assert (tmp_path / "SOUL.md").read_text(encoding="utf-8") == DEFAULT_SOUL_MD
    assert DEFAULT_SOUL_MD.startswith("You are Thoth")


def test_untouched_first_thoth_seed_upgrades_to_finish_the_job_default(tmp_path):
    (tmp_path / "SOUL.md").write_text(THOTH_V1_SEED.replace("\u2014", "--"), encoding="utf-8")

    _ensure_default_soul_md(tmp_path)

    assert "Finish the job" in (tmp_path / "SOUL.md").read_text(encoding="utf-8")


def test_customized_soul_is_left_alone(tmp_path):
    custom = HERMES_SEED + "\nAlways answer like a pirate."
    (tmp_path / "SOUL.md").write_text(custom, encoding="utf-8")

    _ensure_default_soul_md(tmp_path)

    assert (tmp_path / "SOUL.md").read_text(encoding="utf-8") == custom
