"""Free-model rotation: when the current model is one of a provider's free daily models, the
fallback chain is that provider's other free models, then every other signed-in provider's free
models in Providers-page order. The ordinary fallback walk (``try_activate_fallback``) does the
switching when a free model runs out or is rate-limited; entries carry ``free_rotation`` so the
switch notice reads "Switched to <Provider>: <model> (free)".

A paid model also ends its chain with the free models, marked ``on_credits_only``: they are
tried only when the account runs out of credits. With Free mode on (``model.free_mode``), only
free models are ever used, so configured paid fallbacks drop out of the chain. Local servers
(Ollama, LM Studio, custom endpoints) are never free models and never rotate in."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

def _lists() -> dict[str, list[str]]:
    """Cached lists only: this runs on the message path, so a missing or stale list refreshes in
    the background and rotation picks it up from the next message."""
    from hermes_cli.free_models import free_models_by_provider
    return free_models_by_provider()


def _provider_order(start: str | None) -> list[str]:
    from hermes_cli.free_models import FREE_MODEL_PROVIDERS
    if start not in FREE_MODEL_PROVIDERS:
        return list(FREE_MODEL_PROVIDERS)
    at = FREE_MODEL_PROVIDERS.index(start)
    return list(FREE_MODEL_PROVIDERS[at + 1:] + FREE_MODEL_PROVIDERS[:at])


def _signed_in_free_models(lists: dict[str, list[str]], start: str | None) -> list[tuple[str, str]]:
    return [(p, m) for p in _provider_order(start) if lists.get(p) and _signed_in(p) for m in lists[p]]


def free_rotation_chain(provider: str, model: str) -> list[dict]:
    """Fallback entries that keep a free model's conversation on free models; [] when *model* is
    not one of *provider*'s free models."""
    slug, model = (provider or "").strip().lower(), (model or "").strip()
    if not model:
        return []
    lists = _lists()
    own = lists.get(slug) or []
    if model not in own:
        return []
    at = own.index(model)
    chain = [(slug, m) for m in own[at + 1:] + own[:at]] + _signed_in_free_models(lists, slug)
    return [{"provider": p, "model": m, "free_rotation": True} for p, m in chain]


def credits_fallback_chain(provider: str, model: str) -> list[dict]:
    """For a paid model: every signed-in provider's free models, tried only once the account is
    out of credits."""
    lists = _lists()
    slug = (provider or "").strip().lower()
    return [{"provider": p, "model": m, "free_rotation": True, "on_credits_only": True}
            for p, m in _signed_in_free_models(lists, slug) if (p, m) != (slug, model)]


def _signed_in(provider: str) -> bool:
    from hermes_cli.models_detect import provider_has_credentials
    return provider_has_credentials(provider)


def with_free_rotation(chain: list[dict], provider: str, model: str) -> list[dict]:
    """*chain* with any earlier rotation entries replaced by the rotation for *model*: a free model
    rotates first, before any configured paid fallback; a paid model keeps its fallbacks and ends
    with the free models for when credits run out. Free mode keeps only free models."""
    from hermes_cli.free_models import free_mode_enabled

    kept = [entry for entry in chain if not entry.get("free_rotation")]
    try:
        free_mode = free_mode_enabled()
        rotation = free_rotation_chain(provider, model)
        if rotation:
            return rotation if free_mode else rotation + kept
        credits = credits_fallback_chain(provider, model)
        if free_mode:
            # A paid model left over from before Free mode: any failure moves to a free one.
            return [{k: v for k, v in entry.items() if k != "on_credits_only"} for entry in credits]
        return kept + credits
    except Exception:
        logger.debug("Free-model rotation unavailable for %s/%s", provider, model, exc_info=True)
        return kept


def skip_for_reason(entry: dict, reason) -> bool:
    """A credits-only free fallback waits for an out-of-credits failure."""
    if not entry.get("on_credits_only"):
        return False
    from agent.error_classifier import FailoverReason
    return reason is not FailoverReason.billing


def switch_notice(provider: str, model: str) -> str:
    from hermes_cli.providers import get_label
    return f"Switched to {get_label(provider)}: {model} (free)"
