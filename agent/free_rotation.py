"""Free-model rotation: when the current model is one of a provider's free daily models, the
fallback chain is that provider's other free models, then every other signed-in provider's free
models in Providers-page order. The ordinary fallback walk (``try_activate_fallback``) does the
switching when a free model runs out or is rate-limited; entries carry ``free_rotation`` so the
switch notice reads "Switched to <Provider>: <model> (free)"."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_FREE_SUFFIXES = (":free", "-free")


def free_rotation_chain(provider: str, model: str) -> list[dict]:
    """Fallback entries that keep a free model's conversation on free models; [] when *model* is
    not one of *provider*'s free models."""
    from hermes_cli.free_models import FREE_MODEL_PROVIDERS, free_models_by_provider

    slug, model = (provider or "").strip().lower(), (model or "").strip()
    if slug not in FREE_MODEL_PROVIDERS or not model:
        return []
    lists = free_models_by_provider()
    # First run: no list yet. A model that names itself free is worth one inline fetch.
    if not any(lists.values()) and model.endswith(_FREE_SUFFIXES):
        lists = free_models_by_provider(blocking=True)
    own = lists.get(slug) or []
    if model not in own:
        return []
    at = own.index(model)
    chain = [(slug, m) for m in own[at + 1:] + own[:at]]
    start = FREE_MODEL_PROVIDERS.index(slug)
    for other in FREE_MODEL_PROVIDERS[start + 1:] + FREE_MODEL_PROVIDERS[:start]:
        if lists.get(other) and _signed_in(other):
            chain += [(other, m) for m in lists[other]]
    return [{"provider": p, "model": m, "free_rotation": True} for p, m in chain]


def _signed_in(provider: str) -> bool:
    from hermes_cli.models_detect import provider_has_credentials
    return provider_has_credentials(provider)


def with_free_rotation(chain: list[dict], provider: str, model: str) -> list[dict]:
    """*chain* with any earlier rotation entries replaced by the rotation for *model*, which goes
    first so a free conversation stays free before any configured paid fallback."""
    kept = [entry for entry in chain if not entry.get("free_rotation")]
    try:
        rotation = free_rotation_chain(provider, model)
    except Exception:
        logger.debug("Free-model rotation unavailable for %s/%s", provider, model, exc_info=True)
        rotation = []
    return rotation + kept


def switch_notice(provider: str, model: str) -> str:
    from hermes_cli.providers import get_label
    return f"Switched to {get_label(provider)}: {model} (free)"
