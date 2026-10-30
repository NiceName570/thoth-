# Local model servers are plain API endpoints

Thoth has no dedicated local-model support. Ollama, LM Studio and other local servers are added
under Settings > Providers > Custom Endpoints and treated like any other API endpoint. Thoth
built a Local Models page, a llama.cpp installer, model downloads and recommendations, and
auto-detection of a running Ollama or LM Studio (October 2026), then removed them (`a504b8add4`,
`a30c2cbd03`; CHANGELOG "Local models"). The maintainer doesn't run local models and wants them
handled the same way as any API.

## Consequences

The Ollama and LM Studio handling still in the agent core (`agent/agent_init.py` num_ctx sizing,
`agent/model_metadata.py`, the `lmstudio` provider plugin) is upstream Hermes code. Leave it as
upstream ships it: don't remove it, and don't build a local-runtime seam or provider capability
around it. Architecture reviews shouldn't propose deepening it.
