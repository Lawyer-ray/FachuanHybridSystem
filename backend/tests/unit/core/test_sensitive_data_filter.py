import logging

from apps.core.logging import SensitiveDataFilter


def test_sensitive_data_filter_scrubs_nested_extras():
    f = SensitiveDataFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
        args=(),
        exc_info=None,
    )
    record.account = "someone@example.com"
    record.errors = {
        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz",
        "nested": {"token": "sk-abcdefghijklmnopqrstuvwxyz123456", "account": "foo@example.com"},
        "value": "sk-abcdefghijklmnopqrstuvwxyz123456",
    }

    assert f.filter(record) is True

    assert record.account == "so***om"
    assert record.errors["authorization"] == "***"
    assert record.errors["nested"]["token"] == "***"
    assert record.errors["nested"]["account"] == "fo***om"
    assert "***" in record.errors["value"]


def test_sensitive_data_filter_scrubs_message_text():
    f = SensitiveDataFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="token=sk-abcdefghijklmnopqrstuvwxyz123456",
        args=(),
        exc_info=None,
    )

    assert f.filter(record) is True
    assert "sk-" not in record.getMessage()
    assert "***" in record.getMessage()
