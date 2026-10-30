"""The fallback route chain: the ordered backups a failed model call moves through, with free-model
rotation built in. The chain lives on the agent (``_fallback_chain`` and ``_fallback_index``);
this module is the only place that builds it, decides the next entry and words the switch.

When the current model is one of a provider's free daily models, the chain is that provider's
other free models, then every other signed-in provider's free models in Providers-page order,
then the configured fallbacks. A paid model keeps its configured fallbacks and ends the chain with
the free models, marked ``on_credits_only``: they are tried only when the account runs out of
credits. With Free mode on (``model.free_mode``), only free models are ever used. Local servers
(Ollama, LM Studio, custom endpoints) are never free models and never rotate in."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _lists() -> dict[str, list[str]]:
    """Cached lists only: this runs on the message path, so a missing or stale list refreshes in
    the background and the chain picks it up on the next rebuild."""
    from hermes_cli.free_models import free_models_by_provider
    return free_models_by_provider()


def _provider_order(start: str | None) -> list[str]:
    from hermes_cli.free_models import FREE_MODEL_PROVIDERS
    if start not in FREE_MODEL_PROVIDERS:
        return list(FREE_MODEL_PROVIDERS)
    at = FREE_MODEL_PROVIDERS.index(start)
    return list(FREE_MODEL_PROVIDERS[at + 1:] + FREE_MODEL_PROVIDERS[:at])


def _signed_in(provider: str) -> bool:
    from hermes_cli.models_detect import provider_has_credentials
    return provider_has_credentials(provider)


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


def build_chain(configured: list[dict], provider: str, model: str) -> list[dict]:
    """*configured* with any earlier rotation entries replaced by the rotation for *model*: a free
    model rotates first, before any configured paid fallback; a paid model keeps its fallbacks and
    ends with the free models for when credits run out. Free mode keeps only free models, and
    stays free-only when the free lists cannot be read."""
    from hermes_cli.free_models import free_mode_enabled

    kept = [entry for entry in configured if not entry.get("free_rotation")]
    try:
        free_mode = free_mode_enabled()
    except Exception:
        logger.debug("Free mode unreadable; keeping the configured chain", exc_info=True)
        return kept
    try:
        rotation = free_rotation_chain(provider, model)
        if rotation:
            return rotation if free_mode else rotation + kept
        credits = credits_fallback_chain(provider, model)
    except Exception:
        logger.debug("Free-model rotation unavailable for %s/%s", provider, model, exc_info=True)
        return [] if free_mode else kept
    if free_mode:
        # A paid model left over from before Free mode: any failure moves to a free one.
        return [{k: v for k, v in entry.items() if k != "on_credits_only"} for entry in credits]
    return kept + credits


def _entry_key(entry: dict) -> tuple[str, str]:
    return (str(entry.get("provider") or "").strip().lower(), str(entry.get("model") or "").strip())


def rebuild(agent, configured: list[dict], provider: str, model: str) -> list[dict]:
    """Put the chain for *provider*/*model* on the agent. Off a fallback it starts from the top; on
    an active fallback it continues after the model in use, wherever the rebuilt chain has it, so a
    refreshed free list never sends the next failure back to a model that already failed."""
    chain = build_chain(configured, provider, model)
    agent._fallback_chain = chain
    agent._fallback_model = chain[0] if chain else None  # legacy attribute (tests, external callers)
    agent._credits_fallback_at = None
    if not getattr(agent, "_fallback_activated", False):
        agent._fallback_index = 0
        return chain
    current = _entry_key({"provider": getattr(agent, "provider", ""), "model": getattr(agent, "model", "")})
    keys = [_entry_key(entry) for entry in chain]
    if current in keys:
        agent._fallback_index = keys.index(current) + 1
    else:
        agent._fallback_index = min(int(getattr(agent, "_fallback_index", 0) or 0), len(chain))
    return chain


def next_entry(agent, reason) -> dict | None:
    """The next entry to try for a failure of *reason*, advancing the chain; None when none is left.

    Credits-only free models close the chain. A failure that is not out-of-credits stops there and
    holds them, so an out-of-credits failure later in the turn still reaches them."""
    from agent.error_classifier import FailoverReason

    chain = agent._fallback_chain
    held = getattr(agent, "_credits_fallback_at", None)
    if reason is FailoverReason.billing and agent._fallback_index >= len(chain) and held is not None:
        agent._fallback_index, agent._credits_fallback_at = held, None
    if agent._fallback_index >= len(chain):
        return None
    entry = chain[agent._fallback_index]
    if entry.get("on_credits_only") and reason is not FailoverReason.billing:
        agent._credits_fallback_at = agent._fallback_index
        agent._fallback_index = len(chain)
        return None
    agent._fallback_index += 1
    return entry


def configured_entries(chain: list[dict]) -> list[dict]:
    """The entries the user configured; free-model rotation is implied, so banners leave it out."""
    return [entry for entry in chain if not entry.get("free_rotation")]


def switch_notice(entry: dict, provider: str, model: str, *, old_provider: str, old_model: str,
                  reason_text: str, retry_in: int | None = None) -> str:
    """What the user sees when the chain moves to *entry*, bound as *provider*/*model*."""
    if entry.get("free_rotation"):
        from hermes_cli.providers import get_label
        return f"Switched to {get_label(provider)}: {model} (free)"
    notice = (f"⚠️ Model fallback: {old_model} via {old_provider} unavailable "
              f"({reason_text}); using {model} via {provider}.")
    if retry_in is not None:
        notice += f" Primary retry eligible in ~{retry_in} s; recovery is not guaranteed."
    return notice
