"""诉讼文书输出模型、证据清单占位符服务、法院登录网关测试。"""

from __future__ import annotations

from apps.documents.services.generation.outputs import (
    PartyInfo,
    ComplaintOutput,
    DefenseOutput,
    ExecutionRequestOutput,
)
from apps.documents.services.evidence.evidence_list_placeholder_service import (
    LEGAL_STATUS_DISPLAY,
    LEGAL_STATUS_ORDER,
)
from apps.automation.services.token.court_login_gateway import (
    CourtLoginGateway,
    CourtZxfwLoginGateway,
)


class TestPartyInfo:
    """PartyInfo Pydantic 模型测试。"""

    def test_creation(self) -> None:
        party = PartyInfo(name="张三", role="原告")
        assert party.name == "张三"
        assert party.role == "原告"
        assert party.id_number == ""
        assert party.address == ""

    def test_with_all_fields(self) -> None:
        party = PartyInfo(
            name="张三",
            role="原告",
            id_number="440xxx",
            address="广东省佛山市",
        )
        assert party.id_number == "440xxx"
        assert party.address == "广东省佛山市"


class TestComplaintOutput:
    """ComplaintOutput Pydantic 模型测试。"""

    def test_creation(self) -> None:
        output = ComplaintOutput(
            title="民事起诉状",
            parties=[PartyInfo(name="张三", role="原告")],
            litigation_request="判令被告偿还借款",
            facts_and_reasons="原告与被告系朋友关系",
        )
        assert output.title == "民事起诉状"
        assert len(output.parties) == 1
        assert output.evidence == []

    def test_with_evidence(self) -> None:
        output = ComplaintOutput(
            title="起诉状",
            parties=[],
            litigation_request="test",
            facts_and_reasons="test",
            evidence=["借条", "转账记录"],
        )
        assert len(output.evidence) == 2


class TestDefenseOutput:
    """DefenseOutput Pydantic 模型测试。"""

    def test_creation(self) -> None:
        output = DefenseOutput(
            title="民事答辩状",
            parties=[PartyInfo(name="李四", role="被告")],
            defense_opinion="不同意原告的诉讼请求",
            defense_reasons="原告所述与事实不符",
        )
        assert output.title == "民事答辩状"
        assert output.defense_opinion == "不同意原告的诉讼请求"


class TestExecutionRequestOutput:
    """ExecutionRequestOutput Pydantic 模型测试。"""

    def test_defaults(self) -> None:
        output = ExecutionRequestOutput(confirmed_interest=1000)
        assert output.principal is None
        assert output.principal_desc == ""
        assert output.confirmed_interest == 1000
        assert output.attorney_fee == 0
        assert output.rate_type == "lpr"

    def test_with_values(self) -> None:
        output = ExecutionRequestOutput(
            principal=50000.0,
            principal_desc="借款本金",
            confirmed_interest=3000.0,
            attorney_fee=5000.0,
            interest_start_date="2024-01-01",
            rate_type="lpr",
            lpr_multiplier=1.3,
        )
        assert output.principal == 50000.0
        assert output.rate_type == "lpr"
        assert output.lpr_multiplier == 1.3


class TestLegalStatusDisplay:
    """诉讼地位显示映射测试。"""

    def test_plaintiff(self) -> None:
        assert LEGAL_STATUS_DISPLAY["plaintiff"] == "原告"

    def test_defendant(self) -> None:
        assert LEGAL_STATUS_DISPLAY["defendant"] == "被告"

    def test_third(self) -> None:
        assert LEGAL_STATUS_DISPLAY["third"] == "第三人"

    def test_applicant(self) -> None:
        assert LEGAL_STATUS_DISPLAY["applicant"] == "申请人"

    def test_respondent(self) -> None:
        assert LEGAL_STATUS_DISPLAY["respondent"] == "被申请人"

    def test_criminal_defendant(self) -> None:
        assert LEGAL_STATUS_DISPLAY["criminal_defendant"] == "被告人"

    def test_all_statuses_in_order(self) -> None:
        """所有状态都在排序列表中。"""
        for status in LEGAL_STATUS_DISPLAY:
            assert status in LEGAL_STATUS_ORDER


class TestLegalStatusOrder:
    """诉讼地位排序测试。"""

    def test_order_not_empty(self) -> None:
        assert len(LEGAL_STATUS_ORDER) > 0

    def test_order_unique(self) -> None:
        assert len(LEGAL_STATUS_ORDER) == len(set(LEGAL_STATUS_ORDER))

    def test_plaintiff_before_defendant(self) -> None:
        """原告排在被告之前。"""
        assert LEGAL_STATUS_ORDER.index("plaintiff") < LEGAL_STATUS_ORDER.index("defendant")


class TestCourtLoginGateway:
    """CourtLoginGateway Protocol 测试。"""

    def test_protocol_has_login_method(self) -> None:
        """Protocol 定义了 login 方法。"""
        assert hasattr(CourtLoginGateway, "login")

    def test_court_zxfw_login_gateway_creation(self) -> None:
        """创建 CourtZxfwLoginGateway。"""
        gateway = CourtZxfwLoginGateway()
        assert hasattr(gateway, "login")
