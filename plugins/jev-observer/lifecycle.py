"""Runtime enablement checks for work that can outlive plugin discovery."""

from __future__ import annotations


def is_enabled() -> bool:
    """Read the owning profile's opt-in state; failures must not permit observation."""
    try:
        from hermes_cli.config import load_config_readonly

        plugins = (load_config_readonly() or {}).get("plugins", {})
        if not isinstance(plugins, dict):
            return False
        enabled = plugins.get("enabled")
        disabled = plugins.get("disabled")
        return (isinstance(enabled, list) and "jev-observer" in enabled
                and not (isinstance(disabled, list) and "jev-observer" in disabled))
    except Exception:
        return False
