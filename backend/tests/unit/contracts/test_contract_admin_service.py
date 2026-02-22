"""
合同 Admin 服务单元测试
"""

from datetime import date, datetime

import pytest
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone

from apps.contracts.models import (
    Contract,
    ContractAssignment,
    ContractParty,
    PartyRole,
    SupplementaryAgreement,
    SupplementaryAgreementParty,
)
from apps.contracts.services.contract_admin_service import ContractAdminService
from apps.core.enums import CaseType
from apps.core.exceptions import NotFoundError, ValidationException
from apps.reminders.models import Reminder, ReminderType
from tests.factories import ClientFactory, ContractFactory, LawyerFactory


@pytest.mark.django_db
class TestContractAdminService:
    """合同 Admin 服务测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = ContractAdminService()

    def test_renew_advisor_contract_success(self):
        """测试续签常法顾问合同成功"""
        # 创建常法顾问合同
        original_start_date = date(2025, 4, 1)
        original_end_date = date(2026, 3, 31)

        original_contract = ContractFactory(
            name="测试常法顾问合同",
            case_type=CaseType.ADVISOR,
            start_date=original_start_date,
            end_date=original_end_date,
        )

        # 添加当事人
        client = ClientFactory()
        ContractParty.objects.create(contract=original_contract, client=client, role=PartyRole.PRINCIPAL)  # type: ignore[misc]

        # 添加律师指派
        lawyer = LawyerFactory()
        ContractAssignment.objects.create(contract=original_contract, lawyer=lawyer, is_primary=True, order=0)  # type: ignore[misc]

        # 添加提醒
        Reminder.objects.create(  # type: ignore[misc]
            contract=original_contract,
            reminder_type=ReminderType.HEARING,
            content="测试提醒",
            due_at=timezone.make_aware(datetime(2025, 5, 1, 0, 0, 0)),
        )

        # 执行续签
        new_contract = self.service.renew_advisor_contract(original_contract.id)  # type: ignore[attr-defined]

        # 验证新合同基本信息
        assert new_contract.id != original_contract.id  # type: ignore[attr-defined]
        assert new_contract.name == original_contract.name
        assert new_contract.case_type == CaseType.ADVISOR
        assert new_contract.status == original_contract.status
        assert new_contract.is_archived is False

        # 验证日期增加一年
        expected_start_date = original_start_date + relativedelta(years=1)
        expected_end_date = original_end_date + relativedelta(years=1)
        assert new_contract.start_date == expected_start_date
        assert new_contract.end_date == expected_end_date

        # 验证当事人被复制
        new_parties = new_contract.contract_parties.all()
        assert new_parties.count() == 1
        assert new_parties.first().client_id == client.id  # type: ignore[attr-defined]
        assert new_parties.first().role == PartyRole.PRINCIPAL

        # 验证律师指派被复制
        new_assignments = new_contract.assignments.all()
        assert new_assignments.count() == 1
        assert new_assignments.first().lawyer_id == lawyer.id  # type: ignore[attr-defined]
        assert new_assignments.first().is_primary is True

        # 验证提醒被复制且日期增加一年
        new_reminders = new_contract.reminders.all()
        assert new_reminders.count() == 1
        reminder = new_reminders.first()
        assert reminder.reminder_type == ReminderType.HEARING
        assert reminder.content == "测试提醒"
        expected_due_at = timezone.make_aware(datetime(2025, 5, 1, 0, 0, 0)) + relativedelta(years=1)
        assert reminder.due_at == expected_due_at

    def test_renew_advisor_contract_with_supplementary_agreements(self):
        """测试续签包含补充协议的常法顾问合同"""
        original_contract = ContractFactory(
            case_type=CaseType.ADVISOR, start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)
        )

        # 创建补充协议
        agreement = SupplementaryAgreement.objects.create(contract=original_contract, name="测试补充协议")  # type: ignore[misc]

        # 添加补充协议当事人
        client = ClientFactory()
        SupplementaryAgreementParty.objects.create(  # type: ignore[misc]
            supplementary_agreement=agreement, client=client, role=PartyRole.PRINCIPAL
        )

        # 执行续签
        new_contract = self.service.renew_advisor_contract(original_contract.id)  # type: ignore[attr-defined]

        # 验证补充协议被复制
        new_agreements = new_contract.supplementary_agreements.all()
        assert new_agreements.count() == 1
        new_agreement = new_agreements.first()
        assert new_agreement.name == "测试补充协议"

        # 验证补充协议当事人被复制
        new_agreement_parties = new_agreement.parties.all()
        assert new_agreement_parties.count() == 1
        assert new_agreement_parties.first().client_id == client.id  # type: ignore[attr-defined]

    def test_renew_advisor_contract_not_found(self):
        """测试续签不存在的合同"""
        with pytest.raises(NotFoundError) as exc_info:
            self.service.renew_advisor_contract(999)

        assert "合同不存在" in exc_info.value.message  # type: ignore[operator]
        assert exc_info.value.code == "CONTRACT_NOT_FOUND"

    def test_renew_advisor_contract_invalid_type(self):
        """测试续签非常法顾问合同"""
        # 创建民商事合同
        civil_contract = ContractFactory(case_type=CaseType.CIVIL)

        with pytest.raises(ValidationException) as exc_info:
            self.service.renew_advisor_contract(civil_contract.id)  # type: ignore[attr-defined]

        assert "只有常法顾问合同才能续签" in exc_info.value.message  # type: ignore[operator]
        assert exc_info.value.code == "INVALID_CONTRACT_TYPE"

    def test_renew_advisor_contract_date_calculation(self):
        """测试续签日期计算的边界情况"""
        # 测试闰年日期
        original_contract = ContractFactory(
            case_type=CaseType.ADVISOR, start_date=date(2024, 2, 29), end_date=date(2025, 2, 28)  # 闰年2月29日
        )

        new_contract = self.service.renew_advisor_contract(original_contract.id)  # type: ignore[attr-defined]

        # 验证闰年日期正确处理
        assert new_contract.start_date == date(2025, 2, 28)  # 2025年不是闰年
        assert new_contract.end_date == date(2026, 2, 28)

    def test_renew_advisor_contract_no_dates(self):
        """测试续签没有开始/结束日期的合同"""
        original_contract = ContractFactory(case_type=CaseType.ADVISOR, start_date=None, end_date=None)

        new_contract = self.service.renew_advisor_contract(original_contract.id)  # type: ignore[attr-defined]

        # 验证空日期保持为空
        assert new_contract.start_date is None
        assert new_contract.end_date is None

    def test_generate_advisor_contract_name_single_principal(self):
        """测试生成单个委托人的合同名称"""
        principal_names = ["佛山市升平百货有限公司"]
        start_date = date(2025, 1, 1)
        end_date = date(2025, 12, 31)

        name = ContractAdminService.generate_advisor_contract_name(principal_names, start_date, end_date)

        expected = "佛山市升平百货有限公司常法顾问-2025年01月01日至2025年12月31日"
        assert name == expected

    def test_generate_advisor_contract_name_multiple_principals(self):
        """测试生成多个委托人的合同名称"""
        principal_names = ["佛山市升平百货有限公司", "王小贤"]
        start_date = date(2026, 4, 1)
        end_date = date(2027, 3, 31)

        name = ContractAdminService.generate_advisor_contract_name(principal_names, start_date, end_date)

        expected = "佛山市升平百货有限公司、王小贤常法顾问-2026年04月01日至2027年03月31日"
        assert name == expected

    def test_generate_advisor_contract_name_date_formatting(self):
        """测试合同名称日期格式化"""
        principal_names = ["测试公司"]
        start_date = date(2025, 2, 5)  # 测试单位数月日
        end_date = date(2025, 12, 25)

        name = ContractAdminService.generate_advisor_contract_name(principal_names, start_date, end_date)

        expected = "测试公司常法顾问-2025年02月05日至2025年12月25日"
        assert name == expected
