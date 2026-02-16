import json
import logging


def test_json_formatter_uses_utc_z_timestamp():
    from apps.core.logging import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert payload["timestamp"].endswith("Z")
