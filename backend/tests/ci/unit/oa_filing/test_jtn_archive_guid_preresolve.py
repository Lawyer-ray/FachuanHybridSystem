"""归档 Playwright 链路的案号 → GUID 纯 HTTP 预解析（_resolve_project_id）单测。

覆盖：唯一命中直达 / 多命中与 0 命中回退弹窗 / 查询异常回退 / 空案号短路。
JtnCaseGuidScript.lookup_case_guids 打桩，无网络。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from apps.oa_filing.services.oa_scripts.jtn.archive.service import JtnArchiveScript

_GUID_A = "b0219b56-3968-48a8-8e12-3ca86bf160ce"
_GUID_B = "0f2b7a11-1111-2222-3333-444455556666"
_CASE_NO = "2026TEST0001"


def _make_script() -> JtnArchiveScript:
    return JtnArchiveScript(account="acc", password="p")


class TestResolveProjectId:
    @pytest.mark.asyncio
    async def test_single_hit_returns_guid(self):
        script = _make_script()
        with patch(
            "apps.oa_filing.services.oa_scripts.jtn.case_guid.service.JtnCaseGuidScript.lookup_case_guids",
            new=AsyncMock(return_value=[_GUID_A]),
        ) as mock_lookup:
            assert await script._resolve_project_id(_CASE_NO) == _GUID_A
        mock_lookup.assert_awaited_once_with(_CASE_NO)

    @pytest.mark.asyncio
    async def test_multi_hit_returns_none(self):
        script = _make_script()
        with patch(
            "apps.oa_filing.services.oa_scripts.jtn.case_guid.service.JtnCaseGuidScript.lookup_case_guids",
            new=AsyncMock(return_value=[_GUID_B, _GUID_A]),
        ):
            assert await script._resolve_project_id(_CASE_NO) is None

    @pytest.mark.asyncio
    async def test_zero_hit_returns_none(self):
        script = _make_script()
        with patch(
            "apps.oa_filing.services.oa_scripts.jtn.case_guid.service.JtnCaseGuidScript.lookup_case_guids",
            new=AsyncMock(return_value=[]),
        ):
            assert await script._resolve_project_id(_CASE_NO) is None

    @pytest.mark.asyncio
    async def test_lookup_error_returns_none(self):
        """查询异常（如仅扫码账号缓存失效）必须吞掉并回退弹窗，不得打断归档流程。"""
        script = _make_script()
        with patch(
            "apps.oa_filing.services.oa_scripts.jtn.case_guid.service.JtnCaseGuidScript.lookup_case_guids",
            new=AsyncMock(side_effect=RuntimeError("OA 会话无法建立")),
        ):
            assert await script._resolve_project_id(_CASE_NO) is None

    @pytest.mark.asyncio
    async def test_empty_case_no_short_circuits(self):
        script = _make_script()
        with patch(
            "apps.oa_filing.services.oa_scripts.jtn.case_guid.service.JtnCaseGuidScript.lookup_case_guids",
            new=AsyncMock(side_effect=AssertionError("不应发起查询")),
        ):
            assert await script._resolve_project_id("") is None
            assert await script._resolve_project_id(None) is None  # type: ignore[arg-type]
