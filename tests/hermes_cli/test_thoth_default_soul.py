"""Contract: Thoth's default identity replaces an untouched upstream Hermes SOUL.md, never a custom one."""

from hermes_cli.config import _ensure_default_soul_md
from hermes_cli.default_soul import DEFAULT_SOUL_MD

HERMES_SEED = DEFAULT_SOUL_MD.replace("You are Thoth, a personal AI agent.", "You are Hermes Agent, built by Nous Research.")


def test_untouched_hermes_seed_upgrades_to_thoth(tmp_path):
    (tmp_path / "SOUL.md").write_text(HERMES_SEED, encoding="utf-8")

    _ensure_default_soul_md(tmp_path)

    assert (tmp_path / "SOUL.md").read_text(encoding="utf-8").startswith("You are Thoth")


def test_customized_soul_is_left_alone(tmp_path):
    custom = HERMES_SEED + "\nAlways answer like a pirate."
    (tmp_path / "SOUL.md").write_text(custom, encoding="utf-8")

    _ensure_default_soul_md(tmp_path)

    assert (tmp_path / "SOUL.md").read_text(encoding="utf-8") == custom
