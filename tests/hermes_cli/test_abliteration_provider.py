"""abliteration.ai resolves as a first-class provider so a pasted ABLITERATION_API_KEY is used."""

from __future__ import annotations


def test_resolve_provider_full_recognizes_abliteration():
    from hermes_cli.providers import resolve_provider_full

    pdef = resolve_provider_full("abliteration", {}, [])
    assert pdef is not None
    assert pdef.id == "abliteration"
    assert pdef.base_url == "https://api.abliteration.ai/v1"
    assert "ABLITERATION_API_KEY" in pdef.api_key_env_vars


def test_abliterated_alias_resolves_to_abliteration():
    from hermes_cli.providers import resolve_provider_full

    pdef = resolve_provider_full("abliterated", {}, [])
    assert pdef is not None and pdef.id == "abliteration"
