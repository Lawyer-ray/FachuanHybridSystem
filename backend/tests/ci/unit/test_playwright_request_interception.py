"""Test that Playwright request interception can capture /csi/search POST payload."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, call

import pytest

class FakeRequest:
    """Minimal mock of playwright.sync_api.Request."""

    def __init__(self, url: str, method: str, post_data: str | None = None) -> None:
        self.url = url
        self.method = method
        self._post_data = post_data

    @property
    def post_data(self) -> str | None:
        return self._post_data

class TestPlaywrightRequestInterception:
    """Verify the request interception pattern works."""

    def test_intercept_csi_search_post(self) -> None:
        """Simulate page.on('request') capturing a /csi/search POST."""
        intercepted: dict[str, Any] | None = None
        captured_payloads: list[dict[str, Any]] = []

        def on_request(request: FakeRequest) -> None:
            nonlocal intercepted
            if "/csi/search" in request.url and request.method == "POST":
                if request.post_data:
                    intercepted = json.loads(request.post_data)
                    captured_payloads.append(intercepted)

        # Simulate various requests
        requests = [
            FakeRequest("https://law.wkinfo.com.cn/judgment-documents/list", "GET"),
            FakeRequest(
                "https://law.wkinfo.com.cn/csi/search",
                "POST",
                json.dumps(
                    {
                        "query": {
                            "queryString": 'bodyExtend:(("竞业限制"))',
                            "filterDates": [],
                            "filterQueries": [
                                'court:(("007000000广东省/021020000广东省广州市中级人民法院辖区/021020060广东省广州市天河区人民法院"))',
                                "courtLevel:((4))",
                                "instancecode:((001))",
                            ],
                        },
                        "searchScope": {"treeNodeIds": []},
                        "pageInfo": {"limit": 100, "offset": 0},
                        "indexId": "law.case",
                    }
                ),
            ),
            FakeRequest("https://law.wkinfo.com.cn/static/app.js", "GET"),
        ]

        for req in requests:
            on_request(req)

        assert intercepted is not None
        assert intercepted["query"]["queryString"] == 'bodyExtend:(("竞业限制"))'
        assert len(intercepted["query"]["filterQueries"]) == 3
        assert intercepted["indexId"] == "law.case"
        assert len(captured_payloads) == 1

    def test_ignore_non_csi_requests(self) -> None:
        """Non /csi/search requests should be ignored."""
        intercepted: dict[str, Any] | None = None

        def on_request(request: FakeRequest) -> None:
            nonlocal intercepted
            if "/csi/search" in request.url and request.method == "POST":
                if request.post_data:
                    intercepted = json.loads(request.post_data)

        requests = [
            FakeRequest("https://law.wkinfo.com.cn/api/other", "POST", '{"key":"value"}'),
            FakeRequest("https://law.wkinfo.com.cn/csi/search", "GET"),
        ]

        for req in requests:
            on_request(req)

        assert intercepted is None

    def test_payload_pagination_override(self) -> None:
        """Verify we can override pagination on intercepted payload."""
        import copy

        original = {
            "query": {"queryString": "simple:((test))"},
            "pageInfo": {"limit": 100, "offset": 0},
            "indexId": "law.case",
        }

        def build_payload_from_raw(raw: dict[str, Any], *, limit: int, offset: int) -> dict[str, Any]:
            payload = copy.deepcopy(raw)
            page_info = payload.setdefault("pageInfo", {})
            page_info["limit"] = limit
            page_info["offset"] = offset
            return payload

        page1 = build_payload_from_raw(original, limit=50, offset=0)
        page2 = build_payload_from_raw(original, limit=50, offset=50)

        assert page1["pageInfo"] == {"limit": 50, "offset": 0}
        assert page2["pageInfo"] == {"limit": 50, "offset": 50}
        # Original unchanged
        assert original["pageInfo"] == {"limit": 100, "offset": 0}

    def test_extract_keyword_from_payload(self) -> None:
        """Verify keyword extraction from intercepted payload queryString."""
        import re

        def extract_keyword(payload: dict[str, Any] | None) -> str:
            if not payload:
                return ""
            qs = str((payload.get("query") or {}).get("queryString") or "").strip()
            cleaned = re.sub(r"^\w+:", "", qs)
            cleaned = cleaned.replace("((", "").replace("))", "").replace('"', "").strip()
            return cleaned[:200]

        # Test various queryString formats
        assert extract_keyword({"query": {"queryString": 'bodyExtend:(("竞业限制"))'}}) == "竞业限制"
        assert extract_keyword({"query": {"queryString": "simple:((借款合同))"}}) == "借款合同"
        # For complex multi-field queries, extraction simplifies for display
        result = extract_keyword({"query": {"queryString": 'title:(("合同纠纷")) AND courtOpinion:((("违约")))'}})
        assert "合同纠纷" in result
        assert "违约" in result
        assert extract_keyword(None) == ""
