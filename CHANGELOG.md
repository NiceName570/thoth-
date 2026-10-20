# Changelog

Everything Thoth changes on top of the agent it was built from. Built by [NiceName570](https://github.com/NiceName570).

## 0.1.0 (2026-10-16)

The first release with a Windows installer. [Download it](https://github.com/NiceName570/thoth-/releases/tag/v0.1.0).

### Free models
- **Free-model rotation.** When a free model runs out or is rate-limited, the chat moves to the provider's next free model, then to the next signed-in provider with free models, in Providers-page order. The chat shows "Switched to <Provider>: <model> (free)".
- **Free mode** in the model menu, off by default: only free models are listed and used, with no paid fallback. Turning it off returns to the model in use before.
- A paid model's fallback chain ends with the free models, used only when the account runs out of credits.
- Cline, Nous, OpenRouter, Kilo Code and OpenCode Zen carry a "Free daily models" badge and lead the Providers page.
- Free-model lists come from each provider's catalog, refreshed once a day and whenever the model menu opens on a list older than a day. Free models are listed and marked in the menu.
- An account that reports no credits sees only its free models; a provider that can't report credits shows every model with the free ones marked. Local and custom endpoints never count as free.

### Providers
- "Get a key" links open in your browser again (they did nothing before), and each provider links to its own API key page.
- Ollama and LM Studio are no longer auto-detected; add them under Settings > Providers > Custom Endpoints. The API-keys page's "Local / custom endpoint" row opens Custom Endpoints.
- The 64K Ollama context cap is gone: the endpoint's Context setting decides the window, and Auto uses the model's own.
- "Eject Ollama models" keeps working with an Ollama added as a custom endpoint.

### Windows installer
- One installer `.exe` with Python and every dependency inside. It installs to Program Files with a Start menu shortcut, a desktop shortcut and an uninstaller.
- Thoth has its own app ID and update feed (this repository's releases), so it installs next to Hermes Agent instead of replacing it, and never pulls another app's updates.
- App settings live in `%APPDATA%\Thoth`; conversations, memories and keys stay in `%LOCALAPPDATA%\hermes`. Uninstalling keeps both.
- Voice add-ons that need a compiler or overlong file paths (ElevenLabs, WeChat voice, Daytona sandboxes) install on demand instead of shipping in the installer.

### Edge read-aloud ([#8](https://github.com/NiceName570/thoth-/pull/8))
- Edge read-aloud retries when Microsoft's new speech host throttles, and the voice picker lists every Edge voice.

### Docs
- README with screenshots of rotation, Free mode, the Providers page and Memories, and a Download button instead of terminal install commands.
- Jev Observer guide with setup, a worked example and every command.

### Earlier work in this release

#### Thoth name and Windows-first desktop ([#1](https://github.com/NiceName570/thoth-/pull/1), [#4](https://github.com/NiceName570/thoth-/pull/4))
- The desktop app, CLI and TUI output, agent prompts, docs and locales say Thoth, with new Thoth artwork and app icon. The `hermes` command, `HERMES_*` variables and the `~/.hermes` data folder keep their names so existing setups carry over.
- The first-run installer installs Thoth from this fork and works when launched from PowerShell 7.
- First launch goes straight to a local install; the "connect or install" choice screen is gone.
- Nous Portal is listed as an ordinary provider, and the cloud-only gateway mode is removed.
- Empty chats and panes no longer show oversized name lettering.

#### Local models
- The separate Local Models page, llama.cpp installer, downloads and model recommendations are removed.
- "Eject Ollama models" in the model menu frees RAM/VRAM without restarting Ollama, and only reaches this machine's Ollama.
- Ollama is reached over loopback when `OLLAMA_HOST` is a bind-all address.
- Saved base URLs such as `LM_BASE_URL` show and edit in place on the Keys page; API keys stay hidden.

#### Providers
- Cline (ClinePass subscription and pay-as-you-go keys).
- abliteration.ai ([#2](https://github.com/NiceName570/thoth-/pull/2), merged by hand).
- TypeSafe and DefAPI cards on Settings > Providers ([#6](https://github.com/NiceName570/thoth-/pull/6)).

#### Agent and desktop
- Default persona finishes tasks end to end instead of stopping to re-ask.
- Memories page under Scheduled jobs to view, edit and delete saved memories.
- Plan usage meter in the status bar for Codex and Claude plans.

#### Voice
- Edge read-aloud uses Microsoft's new speech endpoint, and falls back to local Piper when Edge fails.

#### Jev observer plugin ([#3](https://github.com/NiceName570/thoth-/pull/3), [#5](https://github.com/NiceName570/thoth-/pull/5), [#7](https://github.com/NiceName570/thoth-/pull/7))
- Opt-in `jev-observer` plugin records a Jev score for each reply in the background; nothing is injected into the conversation.
- Toggle it from the Plugins page; TypeSafe or DefAPI keys go in Settings.
- Contextual mode (`jev-context-v1`) judges each exchange against a window of earlier turns, next to the reply-only baseline.
