import pytest


def test_parse_ollama_chat_response_multiline():
    import httpx

    from apps.core.llm.backends.ollama_protocol import parse_ollama_chat_response

    resp = httpx.Response(
        200,
        text='{"foo": 1}\n{"message": {"role": "assistant", "content": "hi"}}\n',
    )
    data = parse_ollama_chat_response(resp=resp, model="qwen")
    assert data["message"]["content"] == "hi"


def test_parse_ollama_chat_response_invalid_raises():
    import httpx

    from apps.core.llm.backends.ollama_protocol import parse_ollama_chat_response
    from apps.core.llm.exceptions import LLMAPIError

    resp = httpx.Response(200, text="not-json")
    with pytest.raises(LLMAPIError):
        parse_ollama_chat_response(resp=resp, model="qwen")
