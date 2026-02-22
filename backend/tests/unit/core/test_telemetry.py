def test_utc_now_iso_ends_with_z():
    from apps.core.telemetry.time import utc_now_iso

    value = utc_now_iso()
    assert value.endswith("Z")


def test_build_event_extra_includes_request_id_and_timestamp():
    from apps.core.telemetry import build_event_extra  # type: ignore[attr-defined]

    extra = build_event_extra(action="test_action", foo="bar")
    assert extra["action"] == "test_action"
    assert extra["foo"] == "bar"
    assert isinstance(extra["request_id"], str) and extra["request_id"]
    assert isinstance(extra["timestamp"], str) and extra["timestamp"].endswith("Z")
