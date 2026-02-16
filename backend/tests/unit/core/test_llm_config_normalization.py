from apps.core.llm.config import LLMConfig


def test_normalize_api_key_strips_bearer_prefix():
    assert LLMConfig._normalize_api_key("Bearer abc") == "abc"
    assert LLMConfig._normalize_api_key("bearer   abc") == "abc"


def test_normalize_api_key_strips_whitespace():
    assert LLMConfig._normalize_api_key("  abc  ") == "abc"


def test_normalize_base_url_strips_trailing_slash():
    assert LLMConfig._normalize_base_url("https://api.siliconflow.cn/v1/") == "https://api.siliconflow.cn/v1"
