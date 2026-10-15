"""Plugin settings (``plugins.entries.jev-observer.settings``, declared in ``plugin.yaml``
``config_schema`` so the Plugins page renders them). Read per call so edits apply without restart
and each profile reads its own config."""

from __future__ import annotations

from typing import Any

DEFAULTS: dict[str, Any] = {"contextual": True, "context_window": 4, "open_corrections": 3}
_BOUNDS = {"context_window": (0, 12), "open_corrections": (0, 6)}


def current() -> dict[str, Any]:
    from hermes_cli.config import load_config_readonly
    from hermes_cli.plugins_state import _plugin_settings_entry
    entry = _plugin_settings_entry(load_config_readonly() or {}, "jev-observer") or {}
    raw = entry.get("settings") if isinstance(entry.get("settings"), dict) else {}
    out = dict(DEFAULTS)
    if isinstance(raw.get("contextual"), bool):
        out["contextual"] = raw["contextual"]
    for key, (lo, hi) in _BOUNDS.items():
        value = raw.get(key)
        # The Plugins page edits these as generic numbers, so 6.0 means 6.
        if type(value) in (int, float) and float(value).is_integer():
            out[key] = max(lo, min(hi, int(value)))
    return out
