"""Cline provider profile: one Cline API key covers pay-as-you-go credits and a ClinePass
subscription (ClinePass models are the ``cline-pass/*`` ids on the same OpenAI-compatible API)."""

from providers import register_provider
from providers.base import ProviderProfile

cline = ProviderProfile(
    name="cline", aliases=("cline-bot", "clinepass", "cline-pass"), display_name="Cline",
    description="Cline account: ClinePass subscription or pay-as-you-go credits",
    signup_url="https://app.cline.bot/settings/api-keys",
    env_vars=("CLINE_API_KEY", "CLINE_BASE_URL"), base_url="https://api.cline.bot/api/v1",
    auth_type="api_key",
    default_aux_model="cline-pass/glm-5.3-flash",
    # ClinePass ids from docs.cline.bot/getting-started/clinepass; the live catalog adds the
    # pay-as-you-go models when the key can list them.
    fallback_models=(
        "cline-pass/glm-5.3", "cline-pass/glm-5.3-flash", "cline-pass/kimi-k3",
        "cline-pass/deepseek-v4-pro", "cline-pass/deepseek-v4.1-flash", "cline-pass/minimax-m3",
        "cline-pass/qwen3.8-max", "cline-pass/qwen3.7-max", "cline-pass/qwen3.7-plus",
        "cline-pass/mimo-v2.5-pro", "cline-pass/mimo-v2.5",
    ),
)

register_provider(cline)
