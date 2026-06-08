"""案件匹配服务测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.automation.services.sms.case_matcher import CaseMatcher


def _make_sms(case_numbers=None, party_names=None, content=""):
    return SimpleNamespace(
        case_numbers=case_numbers or [],
        party_names=party_names or [],
        content=content,
    )


def _make_case(id=1, name="测试案件", status="active", case_type=None, current_stage=None):
    """创建可哈希的案件对象。"""
    class _Case:
        def __init__(self, id, name, status, case_type, current_stage):
            self.id = id
            self.name = name
            self.status = status
            self.case_type = case_type
            self.current_stage = current_stage
        def __hash__(self):
            return hash(self.id)
        def __eq__(self, other):
            return hasattr(other, "id") and self.id == other.id
    return _Case(id=id, name=name, status=status, case_type=case_type, current_stage=current_stage)


class TestCaseMatcher:
    """CaseMatcher 测试。"""

    def setup_method(self) -> None:
        self.case_service = MagicMock()
        self.document_parser_service = MagicMock()
        self.party_matching_service = MagicMock()
        self.matcher = CaseMatcher(
            case_service=self.case_service,
            document_parser_service=self.document_parser_service,
            party_matching_service=self.party_matching_service,
        )

    def test_match_by_case_number_exact_single_active(self) -> None:
        """案号精确匹配到唯一在办案件。"""
        case = _make_case(id=1, name="张三诉李四", status="active")
        self.case_service.search_cases_by_case_number_internal.return_value = [case]

        sms = _make_sms(case_numbers=["（2025）粤0604民初12345号"])
        result = self.matcher.match(sms)
        assert result is not None
        assert result.id == 1

    def test_match_by_case_number_exact_no_match(self) -> None:
        """案号精确匹配无结果。"""
        self.case_service.search_cases_by_case_number_internal.return_value = []
        self.party_matching_service.find_existing_clients_in_sms.return_value = []
        self.party_matching_service.debug_client_database.return_value = None

        sms = _make_sms(case_numbers=["（2025）粤0604民初99999号"])
        result = self.matcher.match(sms)
        assert result is None

    def test_match_by_case_number_exact_closed_case(self) -> None:
        """案号匹配到已结案案件，返回 None。"""
        from apps.core.models.enums import CaseStatus

        case = _make_case(id=1, name="张三诉李四", status=CaseStatus.CLOSED)
        self.case_service.search_cases_by_case_number_internal.return_value = [case]
        self.party_matching_service.find_existing_clients_in_sms.return_value = []
        self.party_matching_service.debug_client_database.return_value = None

        sms = _make_sms(case_numbers=["（2025）粤0604民初12345号"])
        result = self.matcher.match(sms)
        assert result is None

    def test_match_by_party_names_unique(self) -> None:
        """当事人匹配到唯一案件。"""
        self.case_service.search_cases_by_case_number_internal.return_value = []
        case = _make_case(id=2, name="张三诉李四", status="active")
        # 必须返回所有当事人，因为 _find_all_matching_cases 做双向严格匹配
        matched_clients = [
            SimpleNamespace(id=1, name="张三"),
            SimpleNamespace(id=2, name="李四"),
        ]
        self.party_matching_service.find_existing_clients_in_sms.return_value = matched_clients
        self.party_matching_service.debug_client_database.return_value = None

        # 区分 ACTIVE 和 CLOSED 查询
        def search_by_party(names, status=None):
            from apps.core.models.enums import CaseStatus
            if status == CaseStatus.ACTIVE.value:
                return [case]
            return []

        self.case_service.search_cases_by_party_internal.side_effect = search_by_party
        self.case_service.get_case_party_names_internal.return_value = ["张三", "李四"]

        sms = _make_sms(party_names=["张三", "李四"])
        result = self.matcher.match(sms)
        assert result is not None
        assert result.id == 2

    def test_match_no_party_no_case_number(self) -> None:
        """无案号无当事人，返回 None。"""
        self.party_matching_service.find_existing_clients_in_sms.return_value = []
        self.party_matching_service.debug_client_database.return_value = None

        sms = _make_sms()
        result = self.matcher.match(sms)
        assert result is None

    def test_select_latest_case(self) -> None:
        """多个案件时选择最新的（ID最大）。"""
        cases = [
            _make_case(id=1, name="案件1"),
            _make_case(id=3, name="案件3"),
            _make_case(id=2, name="案件2"),
        ]
        result = self.matcher._select_latest_case(cases)
        assert result.id == 3

    def test_select_latest_case_empty(self) -> None:
        """空列表返回 None。"""
        result = self.matcher._select_latest_case([])
        assert result is None

    def test_detect_case_type_criminal(self) -> None:
        """从案号检测刑事案件类型。"""
        result = self.matcher._detect_case_type_from_number("（2025）粤0605刑初123号")
        from apps.core.models.enums import CaseType

        assert result == CaseType.CRIMINAL

    def test_detect_case_type_civil(self) -> None:
        """从案号检测民事案件类型。"""
        result = self.matcher._detect_case_type_from_number("（2025）粤0605民初123号")
        from apps.core.models.enums import CaseType

        assert result == CaseType.CIVIL

    def test_detect_case_type_administrative(self) -> None:
        """从案号检测行政案件类型。"""
        result = self.matcher._detect_case_type_from_number("（2025）粤0605行初123号")
        from apps.core.models.enums import CaseType

        assert result == CaseType.ADMINISTRATIVE

    def test_detect_case_type_empty(self) -> None:
        """空案号返回 None。"""
        assert self.matcher._detect_case_type_from_number("") is None

    def test_detect_case_stage_enforcement(self) -> None:
        """从案号检测执行阶段。"""
        result = self.matcher._detect_case_stage_from_number("（2025）粤0605执10286号")
        from apps.core.models.enums import CaseStage

        assert result == CaseStage.ENFORCEMENT

    def test_detect_case_stage_second_trial(self) -> None:
        """从案号检测二审阶段。"""
        result = self.matcher._detect_case_stage_from_number("（2025）粤0605民终123号")
        from apps.core.models.enums import CaseStage

        assert result == CaseStage.SECOND_TRIAL

    def test_detect_case_stage_first_trial(self) -> None:
        """从案号检测一审阶段。"""
        result = self.matcher._detect_case_stage_from_number("（2025）粤0605民初123号")
        from apps.core.models.enums import CaseStage

        assert result == CaseStage.FIRST_TRIAL

    def test_detect_case_stage_empty(self) -> None:
        """空案号返回 None。"""
        assert self.matcher._detect_case_stage_from_number("") is None

    def test_is_bankruptcy_case_number(self) -> None:
        """检测破产案件案号。"""
        assert self.matcher._is_bankruptcy_case_number("（2025）粤0605破123号") is True
        assert self.matcher._is_bankruptcy_case_number("（2025）粤0605民初123号") is False
        assert self.matcher._is_bankruptcy_case_number("") is False

    def test_extract_features_from_numbers(self) -> None:
        """从案号列表提取特征。"""
        from apps.core.models.enums import CaseStage, CaseType

        case_type, case_stage, is_bankruptcy = self.matcher._extract_features_from_numbers(
            ["（2025）粤0605民初123号"]
        )
        assert case_type == CaseType.CIVIL
        assert case_stage == CaseStage.FIRST_TRIAL
        assert is_bankruptcy is False

    def test_extract_party_names_from_sms(self) -> None:
        """从短信提取当事人（至少2个）。"""
        sms = _make_sms(party_names=["张三", "李四"])
        result = self.matcher._extract_party_names(sms)
        assert result == ["张三", "李四"]

    def test_extract_party_names_single_from_sms_fallback_to_doc(self) -> None:
        """短信只有1个当事人，回退到文书提取。"""
        sms = _make_sms(party_names=["张三"])
        self.document_parser_service.get_all_document_paths.return_value = ["/path/to/doc.pdf"]
        self.document_parser_service.extract_parties_from_document.return_value = ["张三", "李四"]

        result = self.matcher._extract_party_names(sms)
        assert result == ["张三", "李四"]

    def test_extract_party_names_no_parties(self) -> None:
        """无当事人返回空列表。"""
        sms = _make_sms(party_names=[])
        self.document_parser_service.get_all_document_paths.return_value = []
        result = self.matcher._extract_party_names(sms)
        assert result == []
