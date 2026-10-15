# Changelog

What Thoth changes on top of [Hermes Agent](https://github.com/NousResearch/hermes-agent). Upstream Hermes changes are not listed here; see the upstream repository for those.

## Unreleased

### README and repo tidy-up ([#9](https://github.com/NiceName570/thoth-/pull/9))
- The README opens by saying what Thoth is for, why to pick it over Hermes, and a one-line Windows install.
- Feature and "frictions removed" tables, a repo map, and this changelog.
- Install one-liners and issue links point at this fork instead of upstream Hermes.
- Fixed the "Thoth | Thoth" header and the leftover Hermes name in the Urdu README.

## 0.1.0 (2026-10-14)

### Thoth name and Windows-first desktop ([#1](https://github.com/NiceName570/thoth-/pull/1), [#4](https://github.com/NiceName570/thoth-/pull/4))
- The desktop app, CLI and TUI output, agent prompts, docs and locales say Thoth, with new Thoth artwork and app icon. The `hermes` command, `HERMES_*` variables and the `~/.hermes` data folder keep their names so existing setups carry over.
- The first-run installer installs Thoth from this fork and works when launched from PowerShell 7.
- First launch goes straight to a local install; the "connect or install" choice screen is gone.
- Nous Portal is listed as an ordinary provider, and the cloud-only gateway mode is removed.
- Empty chats and panes no longer show oversized name lettering.

### Local models
- A running Ollama or LM Studio appears in the model menu with no setup, as a normal provider. The separate Local Models page, llama.cpp installer and downloads are removed.
- Auto-detected Ollama context is capped at 64K so models stay on the GPU; an explicit `num_ctx` still wins.
- "Eject Ollama models" in the model menu frees RAM/VRAM without restarting Ollama, and only reaches this machine's Ollama.
- Ollama is reached over loopback when `OLLAMA_HOST` is a bind-all address.
- Saved base URLs such as `LM_BASE_URL` show and edit in place on the Keys page; API keys stay hidden.

### Providers
- Cline (ClinePass subscription and pay-as-you-go keys).
- abliteration.ai ([#2](https://github.com/NiceName570/thoth-/pull/2), merged by hand).
- TypeSafe and DefAPI cards on Settings > Providers ([#6](https://github.com/NiceName570/thoth-/pull/6)).

### Agent and desktop
- Default persona finishes tasks end to end instead of stopping to re-ask.
- Memories page under Scheduled jobs to view, edit and delete saved memories.
- Plan usage meter in the status bar for Codex and Claude plans.

### Voice
- Edge read-aloud uses Microsoft's new speech endpoint, and falls back to local Piper when Edge fails.

### Jev observer plugin ([#3](https://github.com/NiceName570/thoth-/pull/3), [#5](https://github.com/NiceName570/thoth-/pull/5), [#7](https://github.com/NiceName570/thoth-/pull/7))
- Opt-in `jev-observer` plugin records a Jev score for each reply in the background; nothing is injected into the conversation.
- Toggle it from the Plugins page; TypeSafe or DefAPI keys go in Settings.
- Contextual mode (`jev-context-v1`) judges each exchange against a window of earlier turns, next to the reply-only baseline.
