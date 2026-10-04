"""JtnHttpClientMixin 可测单元单测（无网络）。

覆盖按名称查询编排、HTTP 会话重置、候选排序、查询字段解析与登录失败判定。
网络/登录协程全部 mock 或打桩在实例上。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.oa_filing.services.oa_scripts.jtn.case_import import http_client as hc_mod
from apps.oa_filing.services.oa_scripts.jtn.case_import.http_client import JtnHttpClientMixin
from apps.oa_filing.services.oa_scripts.jtn.case_import.models import CaseListFormState, OAListCaseCandidate


def _make_mixin() -> JtnHttpClientMixin:
    mixin = JtnHttpClientMixin()
    mixin._account = "acc"
    mixin._password = "p"
    mixin._http_cookies_cache = None
    mixin._name_search_http_client = None
    mixin._name_search_form_state = None
    mixin._force_playwright_name_search = False
    return mixin


def _candidate(case_no: str, case_name: str, keyid: str) -> OAListCaseCandidate:
    return OAListCaseCandidate(case_no=case_no, case_name=case_name, keyid=keyid, detail_url="")


# ──────────── 登录响应判定 ────────────


class TestIsLoginFailedResponse:
    def test_stayed_on_login_with_form(self):
        resp = SimpleNamespace(
            url="https://ims.jtn.com/member/login.aspx?x=1",
            text="<input name=\"userid\"><input name='password'>",
        )
        assert JtnHttpClientMixin()._is_login_failed_response(resp) is True

    def test_error_text_anywhere(self):
        resp = SimpleNamespace(url="https://ims.jtn.com/other", text="账号或密码错误，请重试")
        assert JtnHttpClientMixin()._is_login_failed_response(resp) is True

    def test_login_url_without_form_is_not_failure(self):
        resp = SimpleNamespace(url="https://ims.jtn.com/member/login.aspx?ok=1", text="正常跳转页")
        assert JtnHttpClientMixin()._is_login_failed_response(resp) is False

    def test_normal_response_is_not_failure(self):
        resp = SimpleNamespace(url="https://ims.jtn.com/project/index.aspx", text="案件列表")
        assert JtnHttpClientMixin()._is_login_failed_response(resp) is False

    def test_login_form_detected_in_first_2500_chars_only(self):
        long_padding = "x" * 3000
        resp = SimpleNamespace(
            url="https://ims.jtn.com/member/login.aspx",
            text=long_padding + '<input name="userid"><input name="password">',
        )
        assert JtnHttpClientMixin()._is_login_failed_response(resp) is False


# ──────────── 查询字段解析 ────────────


class TestResolveCaseNameField:
    def test_present(self):
        payload = {hc_mod._SEARCH_CASE_NAME_FIELD: "", "currentPage": "1"}
        assert JtnHttpClientMixin()._resolve_case_name_field(payload) == hc_mod._SEARCH_CASE_NAME_FIELD

    def test_absent_returns_none(self):
        assert JtnHttpClientMixin()._resolve_case_name_field({"other": "x"}) is None


# ──────────── 候选排序 ────────────


class TestRankNameCandidates:
    def test_exact_name_match_ranks_first_then_case_no(self):
        target = _candidate("B9", "目标公司", "k9")
        unrelated = _candidate("B2", "相关公司", "k2")
        alpha = _candidate("A1", "其他公司", "k1")
        result = JtnHttpClientMixin()._rank_name_candidates(
            keyword="目标公司", candidates=[unrelated, alpha, target], limit=3
        )
        assert result[0] is target
        assert [c.case_no for c in result[1:]] == ["A1", "B2"]

    def test_partial_keyword_match_ranks_by_case_no(self):
        # 名称包含关键词的候选均属第一梯队，按 case_no 排序
        first = _candidate("B2", "目标公司相关", "k2")
        second = _candidate("C1", "目标公司备选", "k1")
        unrelated = _candidate("A9", "无关", "k9")
        result = JtnHttpClientMixin()._rank_name_candidates(
            keyword="目标公司", candidates=[second, unrelated, first], limit=3
        )
        assert [c.case_no for c in result] == ["B2", "C1", "A9"]

    def test_limit_clamped_to_at_least_one(self):
        candidates = [_candidate("A1", "甲", "k1"), _candidate("A2", "乙", "k2")]
        assert len(JtnHttpClientMixin()._rank_name_candidates(keyword="甲", candidates=candidates, limit=0)) == 1
        assert len(JtnHttpClientMixin()._rank_name_candidates(keyword="甲", candidates=candidates, limit=1)) == 1

    def test_same_match_ranked_by_keyid(self):
        first = _candidate("A1", "甲公司", "k2")
        second = _candidate("A1", "甲公司", "k1")
        result = JtnHttpClientMixin()._rank_name_candidates(keyword="甲公司", candidates=[first, second], limit=5)
        assert [c.keyid for c in result] == ["k1", "k2"]


# ──────────── 名称搜索会话重置 ────────────


class TestResetNameSearchHttpSession:
    @pytest.mark.asyncio
    async def test_closes_client_and_clears_state(self):
        mixin = _make_mixin()
        client = MagicMock()
        client.aclose = AsyncMock()
        mixin._name_search_http_client = client
        mixin._name_search_form_state = CaseListFormState(action_url="u", payload={})

        await mixin._reset_name_search_http_session()

        client.aclose.assert_awaited_once()
        assert mixin._name_search_http_client is None
        assert mixin._name_search_form_state is None

    @pytest.mark.asyncio
    async def test_without_client_is_noop(self):
        mixin = _make_mixin()
        await mixin._reset_name_search_http_session()  # 不应抛
        assert mixin._name_search_http_client is None


# ──────────── 按名称查询（HTTP 编排） ────────────


class TestSearchCasesByNameViaHttp:
    def _setup(self, mixin: JtnHttpClientMixin, payload: dict[str, str]) -> tuple[MagicMock, CaseListFormState]:
        client = MagicMock()
        client.post = AsyncMock(
            return_value=MagicMock(text="<html>results</html>", url="https://ims.jtn.com/project/index.aspx")
        )
        form_state = CaseListFormState(action_url="https://ims.jtn.com/project/index.aspx", payload=payload)
        mixin._ensure_name_search_http_session = AsyncMock(return_value=(client, form_state))
        next_state = CaseListFormState(action_url="https://ims.jtn.com/project/index.aspx", payload=dict(payload))
        mixin._extract_form_state = AsyncMock(return_value=next_state)
        return client, form_state

    @pytest.mark.asyncio
    async def test_success_posts_keyword_and_updates_form_state(self):
        mixin = _make_mixin()
        payload = {hc_mod._SEARCH_CASE_NAME_FIELD: "", "currentPage": "9"}
        client, _ = self._setup(mixin, payload)
        candidates = [_candidate("B2", "目标公司相关", "k2"), _candidate("A1", "目标公司", "k1")]
        with patch(
            "apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser.extract_case_candidates_from_search_html",
            MagicMock(return_value=candidates),
        ):
            result = await mixin._search_cases_by_name_via_http(keyword="目标公司", limit=5)

        assert [c.case_no for c in result] == ["A1", "B2"]
        posted_args = client.post.await_args
        assert posted_args.args[0] == "https://ims.jtn.com/project/index.aspx"
        posted_payload = posted_args.kwargs["data"]
        assert posted_payload[hc_mod._SEARCH_CASE_NAME_FIELD] == "目标公司"
        assert posted_payload[hc_mod._SEARCH_CURRENT_PAGE_FIELD] == "1"
        assert mixin._name_search_form_state is mixin._extract_form_state.return_value

    @pytest.mark.asyncio
    async def test_missing_name_field_returns_empty(self):
        mixin = _make_mixin()
        self._setup(mixin, {"other_field": "x"})
        result = await mixin._search_cases_by_name_via_http(keyword="目标公司", limit=5)
        assert result == []
        mixin._ensure_name_search_http_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failure_resets_session_and_reraises(self):
        mixin = _make_mixin()
        client = MagicMock()
        client.post = AsyncMock(side_effect=RuntimeError("post failed"))
        form_state = CaseListFormState(
            action_url="https://ims.jtn.com/project/index.aspx",
            payload={hc_mod._SEARCH_CASE_NAME_FIELD: ""},
        )
        mixin._ensure_name_search_http_session = AsyncMock(return_value=(client, form_state))
        mixin._reset_name_search_http_session = AsyncMock()

        with pytest.raises(RuntimeError, match="post failed"):
            await mixin._search_cases_by_name_via_http(keyword="目标公司", limit=5)

        mixin._reset_name_search_http_session.assert_awaited_once()
