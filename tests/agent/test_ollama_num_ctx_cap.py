"""An Ollama model with no Modelfile num_ctx gets the 64K floor, not its 128K+ GGUF max: a KV cache that
large spills out of VRAM and Ollama runs the model on the CPU."""

from unittest.mock import MagicMock, patch

import httpx

from agent import model_metadata as MM
from agent.model_metadata import MINIMUM_CONTEXT_LENGTH, query_ollama_num_ctx


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


def test_gguf_max_is_capped_at_the_floor():
    data = {"model_info": {"llama.context_length": 131072}, "parameters": ""}
    assert _query(data, "mistral-small-cap-a") == MINIMUM_CONTEXT_LENGTH


def test_modelfile_num_ctx_is_honoured_above_the_floor():
    data = {"model_info": {"llama.context_length": 131072}, "parameters": "num_ctx 98304"}
    assert _query(data, "mistral-small-cap-b") == 98304
