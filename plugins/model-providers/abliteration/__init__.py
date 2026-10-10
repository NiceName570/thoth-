"""abliteration.ai provider profile: OpenAI-compatible chat completions with an ``ak_`` bearer key."""

from providers import register_provider
from providers.base import ProviderProfile

abliteration = ProviderProfile(
    name="abliteration", aliases=("abliteration-ai", "abliterated", "abliterated-ai"),
    display_name="abliteration.ai", description="abliteration.ai — uncensored models, OpenAI-compatible API",
    signup_url="https://abliteration.ai", env_vars=("ABLITERATION_API_KEY", "ABLITERATION_BASE_URL"),
    base_url="https://api.abliteration.ai/v1", auth_type="api_key",
    # No default_aux_model: auxiliary tasks use the main model. [0] is the setup default.
    fallback_models=("abliterated-model",),
)

register_provider(abliteration)
