"""DocumentCaseMatchingService / CourtSMSRecommendationService — 严格匹配与信号推荐测试。

auto_match 纪律：案号规范化后精确相等 + 在办 + 唯一，三者同时满足才自动绑定。
get_recommendations_for_signals 为纯信号函数（案号/当事人/法院名），
与法院短信入口共用同一套评分口径。全部无 DB（mock Case 查询链）。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService
from apps.document_recognition.services.case_matching_service import DocumentCaseMatchingService

_QUERY_NUMBER = "(2024)京01民初123号"  # normalize 后 → （2024）京01民初123号


def _dto(dto_id: int, case_number: str, status: str = "active", name: str = "案件") -> SimpleNamespace:
    return SimpleNamespace(id=dto_id, case_number=case_number, status=status, name=name)


class TestAutoMatchStrictFiltering:
    def _service(self, dtos, search_error=None):
        case_service = MagicMock()
        if search_error is not None:
            case_service.search_cases_by_case_number_internal.side_effect = search_error
        else:
            case_service.search_cases_by_case_number_internal.return_value = dtos
        return DocumentCaseMatchingService(case_service=case_service)

    def test_unique_active_exact_match_hits(self):
        svc = self._service([_dto(1, _QUERY_NUMBER, status="active", name="张三诉李四")])

        match = svc.auto_match(_QUERY_NUMBER)

        assert match == (1, "张三诉李四")

    def test_two_active_exact_matches_return_none(self):
        """两个在办精确命中 → 唯一性不满足，转人工。"""
        svc = self._service([_dto(1, _QUERY_NUMBER), _dto(2, _QUERY_NUMBER)])

        assert svc.auto_match(_QUERY_NUMBER) is None

    def test_unique_closed_case_return_none(self):
        """唯一命中但已结案 → 转人工。"""
        svc = self._service([_dto(1, _QUERY_NUMBER, status="closed")])

        assert svc.auto_match(_QUERY_NUMBER) is None

    def test_icontains_non_exact_match_return_none(self):
        """包含关系（旧弱匹配会命中）不满足精确相等 → 转人工。"""
        svc = self._service([_dto(1, "（2024）京01民初123号之一")])

        assert svc.auto_match(_QUERY_NUMBER) is None

    def test_half_and_full_width_parens_both_normalize_to_exact(self):
        """括号全半角差异经规范化后视为精确相等。"""
        svc = self._service([_dto(1, "（2024）京01民初123号")])

        assert svc.auto_match(_QUERY_NUMBER) == (1, "案件")

    def test_empty_or_blank_case_number_return_none(self):
        svc = self._service([_dto(1, _QUERY_NUMBER)])
        assert svc.auto_match("") is None
        assert svc.auto_match("   ") is None
        assert svc.auto_match(None) is None

    def test_search_exception_return_none(self):
        svc = self._service([], search_error=RuntimeError("db error"))

        assert svc.auto_match(_QUERY_NUMBER) is None


class TestGetRecommendations:
    """无 DB：mock Case.objects 查询链，验证信号驱动的推荐排序。"""

    @staticmethod
    def _make_case(case_id: int, name: str, numbers: list[str], parties: list[str], authorities: list[str]):
        case = MagicMock()
        case.id = case_id
        case.name = name
        case.status = "active"
        case.start_date = None
        case.case_numbers.all.return_value = [SimpleNamespace(number=n) for n in numbers]
        party_mocks = []
        for p in parties:
            pm = MagicMock()
            pm.client = SimpleNamespace(name=p)
            party_mocks.append(pm)
        case.parties.all.return_value = party_mocks
        case.supervising_authorities.all.return_value = [SimpleNamespace(name=a) for a in authorities]
        return case

    def _run(self, cases, **signals):
        queryset = MagicMock()
        queryset.__iter__.return_value = iter(cases)
        queryset.count.return_value = len(cases)
        case_model = MagicMock()
        case_model.objects.filter.return_value.distinct.return_value.prefetch_related.return_value = queryset

        with patch(
            "apps.automation.services.sms.court_sms_recommendation_service.Case", case_model
        ):
            return CourtSMSRecommendationService().get_recommendations_for_signals(**signals)

    def test_signals_with_no_match_domain_returns_empty(self):
        assert (
            self._run(
                [],
                case_numbers=[],
                party_names=[],
                court_name=None,
            )
            == []
        )

    def test_exact_case_number_ranks_first_with_party_and_court_signals(self):
        exact = self._make_case(1, "案号全中案", ["（2025）粤01民初100号"], [], [])
        weak = self._make_case(2, "仅当事人案", [], ["张三"], [])

        results = self._run(
            [weak, exact],
            case_numbers=["(2025)粤01民初100号"],
            party_names=["张三"],
            court_name=None,
        )

        assert results[0].case_id == 1
        assert results[0].score >= 100
        assert any("案号完全匹配" in r for r in results[0].reasons)
        assert any("当事人匹配" in r for r in results[1].reasons)
        # 分数降序
        assert results[0].score >= results[1].score

    def test_court_name_signal_scores(self):
        case = self._make_case(3, "法院名匹配案", [], [], ["佛山市顺德区人民法院"])

        results = self._run([case], case_numbers=[], party_names=[], court_name="佛山市顺德区人民法院")

        assert len(results) == 1
        assert results[0].score >= 40
        assert any("法院名称匹配" in r for r in results[0].reasons)

    def test_signals_keep_top10(self):
        cases = [self._make_case(i, f"案{i}", [], [f"当事人{i}"], []) for i in range(1, 13)]

        results = self._run(cases, case_numbers=[], party_names=["当事人"], court_name=None)

        assert len(results) == 10

    def test_get_recommendations_thin_wrapper_for_sms(self):
        """get_recommendations 是 get_recommendations_for_signals 的薄包装。"""
        case = self._make_case(7, "短信推荐案", ["（2025）粤01民初200号"], [], [])
        queryset = MagicMock()
        queryset.__iter__.return_value = iter([case])
        queryset.count.return_value = 1
        case_model = MagicMock()
        case_model.objects.filter.return_value.distinct.return_value.prefetch_related.return_value = queryset

        sms = MagicMock()
        sms.scraper_task = None  # 跳过 CourtDocument 回退，直接走短信内容正则
        sms.case_numbers = ["(2025)粤01民初200号"]
        sms.party_names = []
        sms.content = "【佛山市顺德区人民法院】您的案件已排期"

        with patch(
            "apps.automation.services.sms.court_sms_recommendation_service.Case", case_model
        ):
            results = CourtSMSRecommendationService().get_recommendations(sms)

        assert len(results) == 1
        assert results[0].case_id == 7


class TestExtractCourtNameFromText:
    def test_extracts_court_name(self):
        text = "佛山市顺德区人民法院出具的传票，案号（2024）粤0604民初1号"
        assert CourtSMSRecommendationService.extract_court_name_from_text(text) == "佛山市顺德区人民法院"

    def test_no_court_returns_none(self):
        assert CourtSMSRecommendationService.extract_court_name_from_text("普通文书无法院") is None
        assert CourtSMSRecommendationService.extract_court_name_from_text("") is None
