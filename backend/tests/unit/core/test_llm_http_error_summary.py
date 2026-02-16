import httpx

from apps.core.llm.backends.http_error_summary import summarize_http_error_response


def test_summarize_http_error_response_from_json():
    req = httpx.Request("GET", "https://example.com")
    resp = httpx.Response(
        400,
        request=req,
        json={"error": {"message": "bad request", "code": "BAD_REQUEST"}},
        headers={"x-request-id": "req_123"},
    )

    summary = summarize_http_error_response(resp)
    assert summary["status_code"] == 400
    assert summary["upstream_request_id"] == "req_123"
    assert summary["upstream_error_code"] == "BAD_REQUEST"
    assert summary["upstream_error_message"] == "bad request"


def test_summarize_http_error_response_from_text_truncates():
    req = httpx.Request("GET", "https://example.com")
    resp = httpx.Response(502, request=req, text="x" * 500)
    summary = summarize_http_error_response(resp, max_text_len=50)
    assert summary["status_code"] == 502
    assert "upstream_error_text" in summary
    assert len(summary["upstream_error_text"]) <= 53
