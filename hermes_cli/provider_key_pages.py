"""Where each API-key provider hands out its keys: the page a Providers card's "Get key" link
opens. Keyed by provider slug, so a credential shared by several providers links each card to
its own provider. A provider missing here keeps the catalog's signup URL."""

API_KEY_PAGES: dict[str, str] = {
    "ai-gateway": "https://vercel.com/d?to=%2F%5Bteam%5D%2F%7E%2Fai-gateway%2Fapi-keys",
    "alibaba": "https://modelstudio.console.alibabacloud.com/?tab=playground#/api-key",
    "anthropic": "https://console.anthropic.com/settings/keys",
    "cline": "https://app.cline.bot/settings/api-keys",
    "copilot": "https://github.com/settings/tokens",
    "deepinfra": "https://deepinfra.com/dash/api_keys",
    "deepseek": "https://platform.deepseek.com/api_keys",
    "fireworks": "https://app.fireworks.ai/settings/users/api-keys",
    "gemini": "https://aistudio.google.com/app/apikey",
    "huggingface": "https://huggingface.co/settings/tokens",
    "kilocode": "https://app.kilo.ai/profile",
    "kimi-coding": "https://platform.moonshot.ai/console/api-keys",
    "kimi-coding-cn": "https://platform.moonshot.cn/console/api-keys",
    "minimax": "https://platform.minimax.io/user-center/basic-information/interface-key",
    "minimax-cn": "https://platform.minimaxi.com/user-center/basic-information/interface-key",
    "novita": "https://novita.ai/settings/key-management",
    "nvidia": "https://build.nvidia.com/settings/api-keys",
    "ollama-cloud": "https://ollama.com/settings/keys",
    "openai-api": "https://platform.openai.com/api-keys",
    "opencode-go": "https://opencode.ai/auth",
    "opencode-zen": "https://opencode.ai/auth",
    "openrouter": "https://openrouter.ai/keys",
    "router": "https://app.router.com/keys",
    "upstage": "https://console.upstage.ai/api-keys",
    "xai": "https://console.x.ai/team/default/api-keys",
}


def api_key_page(provider: str, fallback: str | None) -> str | None:
    return API_KEY_PAGES.get((provider or "").strip().lower(), fallback)
