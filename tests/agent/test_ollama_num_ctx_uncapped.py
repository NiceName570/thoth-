"""An Ollama model with no Modelfile num_ctx gets its own GGUF max: Thoth sets no 64K ceiling, the
endpoint's Context setting is what narrows the window."""

from unittest.mock import MagicMock, patch

import httpx

from agent import model_metadata as MM
from agent.model_metadata import query_ollama_num_ctx


def _query(show_data, model):
    resp = MagicMock(status_code=200)
    resp.json.return_value = show_data
    client = MagicMock()
    client.post.return_value = resp
    client.__enter__ = lambda s: client
    client.__exit__ = lambda s, *a: False
    with patch.object(MM, "detect_local_server_type", return_value="ollama"), \
            patch.object(httpx, "Client", return_value=client):
        return query_ollama_num_ctx(model, "http://127.0.0.1:11434/v1")


def test_gguf_max_is_not_capped():
    data = {"model_info": {"llama.context_length": 131072}, "parameters": ""}
    assert _query(data, "mistral-small-cap-a") == 131072


def test_modelfile_num_ctx_is_honoured_above_the_floor():
    data = {"model_info": {"llama.context_length": 131072}, "parameters": "num_ctx 98304"}
    assert _query(data, "mistral-small-cap-b") == 98304


def _served_window(detected, context_setting, override=None):
    from types import SimpleNamespace

    from agent import agent_init

    agent = SimpleNamespace(base_url="http://127.0.0.1:11434/v1", model="qwen3:14b", api_key="", quiet_mode=True)
    model_cfg = {} if override is None else {"ollama_num_ctx": override}
    with patch.object(agent_init, "query_ollama_num_ctx", return_value=detected):
        agent_init._configure_ollama_num_ctx(agent, model_cfg, context_setting)
    return agent._ollama_num_ctx


def test_auto_context_uses_the_models_own_window():
    assert _served_window(131072, None) == 131072


def test_context_setting_decides_in_both_directions():
    assert _served_window(131072, 32768) == 32768
    assert _served_window(40960, 98304) == 98304


def test_explicit_num_ctx_still_wins():
    assert _served_window(131072, 32768, override=65536) == 65536
