from __future__ import annotations

from apps.core.security.scrub import is_sensitive_key_name, scrub_for_storage


def test_is_sensitive_key_name_handles_keyword_without_false_positive() -> None:
    assert is_sensitive_key_name("keyword") is False
    assert is_sensitive_key_name("searchKeyword") is False
    assert is_sensitive_key_name("company_keyword") is False


def test_is_sensitive_key_name_keeps_sensitive_key_detection() -> None:
    assert is_sensitive_key_name("api_key") is True
    assert is_sensitive_key_name("secretKey") is True
    assert is_sensitive_key_name("accessKey") is True
    assert is_sensitive_key_name("refresh_token") is True


def test_scrub_for_storage_masks_sensitive_fields_only() -> None:
    payload = {
        "keyword": "阿里巴巴",
        "api_key": "sk_example_abcdefghijklmnopqrstuvwxyz",
        "nested": {"accessKey": "abcde12345FGHIJ67890KLMN"},
    }

    scrubbed = scrub_for_storage(payload)
    assert scrubbed["keyword"] == "阿里巴巴"
    assert scrubbed["api_key"] != payload["api_key"]
    assert "***" in scrubbed["api_key"]
    assert scrubbed["nested"]["accessKey"] != payload["nested"]["accessKey"]
    assert "***" in scrubbed["nested"]["accessKey"]
