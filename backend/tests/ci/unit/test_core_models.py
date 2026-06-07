"""
核心模型层测试：覆盖 __str__、@property、自定义方法、约束、验证。

覆盖模型：Case, CaseNumber, SupervisingAuthority, CaseLog, CaseParty,
CaseAssignment, CaseAccessGrant, Reminder, Court, CauseOfAction,
AccountCredential, CaseFolderBinding, CaseMaterialType, SecretCodec
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.cases.models import (
    Case,
    CaseAccessGrant,
    CaseAssignment,
    CaseLog,
    CaseMaterialType,
    CaseNumber,
    CaseParty,
    SupervisingAuthority,
)
from apps.cases.models.material import CaseFolderBinding, CaseMaterialCategory
from apps.core.models import CauseOfAction, Court
from apps.core.security.secret_codec import SecretCodec
from apps.organization.models import AccountCredential
from apps.reminders.models import Reminder
from apps.testing.factories import CaseFactory, CaseLogFactory, ClientFactory, ContractFactory, LawyerFactory

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None  # type: ignore[assignment,misc]


# =====================================================================
# Case 模型
# =====================================================================


class TestCaseModel:
    """Case 模型的 __str__、get_case_chain、clean 方法。"""

    @pytest.mark.django_db
    def test_str_returns_name(self) -> None:
        """__str__ 应返回案件名称。"""
        case = CaseFactory(name="张三诉李四")
        assert str(case) == "张三诉李四"

    @pytest.mark.django_db
    def test_get_case_chain_single_case(self) -> None:
        """无前序案件时，链应只包含自身。"""
        case = CaseFactory()
        chain = case.get_case_chain()
        assert len(chain) == 1
        assert chain[0].pk == case.pk

    @pytest.mark.django_db
    def test_get_case_chain_linear(self) -> None:
        """线性链 A -> B -> C 应返回完整链。"""
        contract = ContractFactory()
        case_a = CaseFactory(name="A", contract=contract)
        case_b = CaseFactory(name="B", contract=contract, previous_case=case_a)
        case_c = CaseFactory(name="C", contract=contract, previous_case=case_b)

        # 从中间节点查询，应返回完整链
        chain = case_b.get_case_chain()
        chain_pks = [c.pk for c in chain]
        assert case_a.pk in chain_pks
        assert case_b.pk in chain_pks
        assert case_c.pk in chain_pks

    @pytest.mark.django_db
    def test_get_case_chain_cycle_detection(self) -> None:
        """环形引用不应导致无限循环。"""
        contract = ContractFactory()
        case_a = CaseFactory(name="A", contract=contract)
        case_b = CaseFactory(name="B", contract=contract, previous_case=case_a)
        case_a.previous_case = case_b
        case_a.save()

        chain = case_a.get_case_chain()
        assert len(chain) >= 2  # 至少返回两个节点，不会无限循环

    @pytest.mark.django_db
    def test_clean_valid_stage(self) -> None:
        """有效 current_stage 不应报错。"""
        case = CaseFactory(current_stage="first_trial")
        case.clean()  # 不应抛出异常

    @pytest.mark.django_db
    def test_clean_none_stage(self) -> None:
        """current_stage 为 None 不应报错。"""
        case = CaseFactory(current_stage=None)
        case.clean()

    @pytest.mark.django_db
    def test_clean_invalid_stage(self) -> None:
        """无效 current_stage 应抛出 ValidationError。"""
        case = CaseFactory(current_stage="nonexistent_stage")
        with pytest.raises(ValidationError):
            case.clean()


# =====================================================================
# CaseNumber 模型
# =====================================================================


class TestCaseNumberModel:
    """CaseNumber 的 __str__ 和 get_full_number。"""

    @pytest.mark.django_db
    def test_str_returns_number(self) -> None:
        case = CaseFactory()
        cn = CaseNumber.objects.create(case=case, number="(2024)京01民初123号")
        assert str(cn) == "(2024)京01民初123号"

    @pytest.mark.django_db
    def test_get_full_number_with_document_name(self) -> None:
        case = CaseFactory()
        cn = CaseNumber.objects.create(case=case, number="123", document_name="民事判决书")
        assert cn.get_full_number() == "123《民事判决书》"

    @pytest.mark.django_db
    def test_get_full_number_without_document_name(self) -> None:
        case = CaseFactory()
        cn = CaseNumber.objects.create(case=case, number="123")
        assert cn.get_full_number() == "123"


# =====================================================================
# SupervisingAuthority 模型
# =====================================================================


class TestSupervisingAuthorityModel:
    """SupervisingAuthority 的 __str__ 四个分支。"""

    @pytest.mark.django_db
    def test_str_with_name_and_type(self) -> None:
        case = CaseFactory()
        sa = SupervisingAuthority.objects.create(case=case, name="北京一中院", authority_type="court")
        result = str(sa)
        assert "北京一中院" in result

    @pytest.mark.django_db
    def test_str_with_name_only(self) -> None:
        case = CaseFactory()
        sa = SupervisingAuthority.objects.create(case=case, name="北京一中院", authority_type="")
        assert str(sa) == "北京一中院"

    @pytest.mark.django_db
    def test_str_unique_constraint(self) -> None:
        """同一案件下不能有重复 name 的主管机关。"""
        case = CaseFactory()
        SupervisingAuthority.objects.create(case=case, name="法院A", authority_type="court")
        with pytest.raises(IntegrityError):
            SupervisingAuthority.objects.create(case=case, name="法院A", authority_type="prosecutor")


# =====================================================================
# CaseLog 提醒属性
# =====================================================================


class TestCaseLogReminderProperties:
    """CaseLog 的 reminder 属性和缓存机制。"""

    @pytest.mark.django_db
    def test_str_format(self) -> None:
        """__str__ 应包含 case_id 和 actor_id。"""
        log = CaseLogFactory()
        result = str(log)
        assert str(log.case_id) in result
        assert str(log.actor_id) in result

    @pytest.mark.django_db
    def test_unsaved_instance_returns_empty(self) -> None:
        """未保存实例的 reminder_entries 应返回空列表。"""
        log = CaseLog(case_id=1, actor_id=1, content="test")
        assert log.reminder_entries == []
        assert log.has_reminders is False
        assert log.reminder_count == 0

    @pytest.mark.django_db
    def test_cache_hit_skips_service_call(self) -> None:
        """预填充缓存后不应调用 ServiceLocator。"""
        log = CaseLogFactory()
        log._cached_exported_reminders = [
            {"reminder_type": "hearing", "due_at": datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)}
        ]

        with patch("apps.core.infrastructure.service_locator.ServiceLocator") as mock_sl:
            assert log.reminder_count == 1
            assert log.has_reminders is True
            mock_sl.get_reminder_service.assert_not_called()

    @pytest.mark.django_db
    def test_reminder_type_with_cached_dict(self) -> None:
        """reminder_type 应从缓存的 dict 中读取。"""
        log = CaseLogFactory()
        log._cached_latest_reminder = {"reminder_type": "hearing", "due_at": datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)}
        assert log.reminder_type == "hearing"

    @pytest.mark.django_db
    def test_reminder_type_none_when_no_reminder(self) -> None:
        """无提醒时 reminder_type 应返回 None。"""
        log = CaseLogFactory()
        log._cached_latest_reminder = None
        assert log.reminder_type is None
        assert log.reminder_time is None

    @pytest.mark.django_db
    def test_reminder_time_extracts_due_at(self) -> None:
        """reminder_time 应提取 due_at 字段。"""
        log = CaseLogFactory()
        dt = datetime.datetime(2026, 6, 15, 10, 0, tzinfo=datetime.timezone.utc)
        log._cached_latest_reminder = {"reminder_type": "hearing", "due_at": dt}
        assert log.reminder_time == dt

    @pytest.mark.django_db
    def test_reminder_time_none_for_non_datetime(self) -> None:
        """due_at 非 datetime 类型时应返回 None。"""
        log = CaseLogFactory()
        log._cached_latest_reminder = {"reminder_type": "hearing", "due_at": "not-a-datetime"}
        assert log.reminder_time is None


# =====================================================================
# Reminder 模型
# =====================================================================


class TestReminderModel:
    """Reminder 的 clean 方法、__str__、约束。"""

    @pytest.mark.django_db
    def test_clean_single_binding_passes(self) -> None:
        """只绑定一个目标时 clean 应通过。"""
        case = CaseFactory()
        r = Reminder(case=case, reminder_type="hearing", content="test", due_at=datetime.datetime.now(datetime.timezone.utc))
        r.clean()  # 不应抛出异常

    @pytest.mark.django_db
    def test_clean_two_bindings_raises(self) -> None:
        """绑定两个目标时 clean 应抛出 ValidationError。"""
        contract = ContractFactory()
        case = CaseFactory(contract=contract)
        r = Reminder(
            contract=contract, case=case,
            reminder_type="hearing", content="test",
            due_at=datetime.datetime.now(datetime.timezone.utc),
        )
        with pytest.raises(ValidationError):
            r.clean()

    @pytest.mark.django_db
    def test_str_with_case(self) -> None:
        case = CaseFactory()
        r = Reminder(case=case, reminder_type="hearing", due_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc))
        result = str(r)
        assert "case:" in result
        assert "hearing" in result

    @pytest.mark.django_db
    def test_str_unbound(self) -> None:
        """无绑定时应包含 'unbound'。"""
        r = Reminder(reminder_type="other", due_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc))
        result = str(r)
        assert "unbound" in result

    @pytest.mark.django_db
    def test_db_constraint_two_bindings(self) -> None:
        """数据库约束应阻止同时绑定 case 和 contract。"""
        contract = ContractFactory()
        case = CaseFactory(contract=contract)
        with pytest.raises(IntegrityError):
            Reminder.objects.create(
                contract=contract, case=case,
                reminder_type="hearing", content="test",
                due_at=datetime.datetime.now(datetime.timezone.utc),
            )


# =====================================================================
# Court 模型
# =====================================================================


class TestCourtModel:
    """Court 的 __str__ 和 full_path。"""

    @pytest.mark.django_db
    def test_str_returns_name(self) -> None:
        court = Court.objects.create(name="北京一中院", code="BJ01", level=3, is_active=True)
        assert str(court) == "北京一中院"

    @pytest.mark.django_db
    def test_full_path_root(self) -> None:
        """无父级时 full_path 应只返回自身名称。"""
        court = Court.objects.create(name="北京一中院", code="BJ01", level=3, is_active=True)
        assert court.full_path == "北京一中院"

    @pytest.mark.django_db
    def test_full_path_two_levels(self) -> None:
        parent = Court.objects.create(name="北京市高院", code="BJ", level=2, is_active=True)
        child = Court.objects.create(name="北京一中院", code="BJ01", level=3, parent=parent, is_active=True)
        assert child.full_path == "北京市高院 > 北京一中院"

    @pytest.mark.django_db
    def test_full_path_three_levels(self) -> None:
        root = Court.objects.create(name="最高法院", code="SC", level=1, is_active=True)
        mid = Court.objects.create(name="北京市高院", code="BJ", level=2, parent=root, is_active=True)
        leaf = Court.objects.create(name="北京一中院", code="BJ01", level=3, parent=mid, is_active=True)
        assert leaf.full_path == "最高法院 > 北京市高院 > 北京一中院"


# =====================================================================
# CauseOfAction 模型
# =====================================================================


class TestCauseOfActionModel:
    """CauseOfAction 的 __str__ 和 full_path。"""

    @pytest.mark.django_db
    def test_str_format(self) -> None:
        coa = CauseOfAction.objects.create(name="合同纠纷", code="001", case_type="civil", is_active=True)
        result = str(coa)
        assert "合同纠纷" in result

    @pytest.mark.django_db
    def test_full_path_root(self) -> None:
        coa = CauseOfAction.objects.create(name="合同纠纷", code="001", case_type="civil", is_active=True)
        assert coa.full_path == "合同纠纷"

    @pytest.mark.django_db
    def test_full_path_nested(self) -> None:
        parent = CauseOfAction.objects.create(name="合同纠纷", code="001", case_type="civil", is_active=True)
        child = CauseOfAction.objects.create(name="买卖合同纠纷", code="001-01", case_type="civil", parent=parent, is_active=True)
        assert child.full_path == "合同纠纷 > 买卖合同纠纷"


# =====================================================================
# AccountCredential 模型
# =====================================================================


class TestAccountCredentialModel:
    """AccountCredential 的 __str__ 和 success_rate。"""

    @pytest.mark.django_db
    def test_str_format(self) -> None:
        lawyer = LawyerFactory()
        cred = AccountCredential.objects.create(lawyer=lawyer, site_name="法院网", account="test_user")
        assert str(cred) == "法院网 - test_user"

    @pytest.mark.django_db
    def test_success_rate_zero_attempts(self) -> None:
        lawyer = LawyerFactory()
        cred = AccountCredential.objects.create(lawyer=lawyer, site_name="test", account="user")
        assert cred.success_rate == 0.0

    @pytest.mark.django_db
    def test_success_rate_all_success(self) -> None:
        lawyer = LawyerFactory()
        cred = AccountCredential.objects.create(
            lawyer=lawyer, site_name="test", account="user",
            login_success_count=10, login_failure_count=0,
        )
        assert cred.success_rate == 1.0

    @pytest.mark.django_db
    def test_success_rate_all_failure(self) -> None:
        lawyer = LawyerFactory()
        cred = AccountCredential.objects.create(
            lawyer=lawyer, site_name="test", account="user",
            login_success_count=0, login_failure_count=5,
        )
        assert cred.success_rate == 0.0

    @pytest.mark.django_db
    def test_success_rate_mixed(self) -> None:
        lawyer = LawyerFactory()
        cred = AccountCredential.objects.create(
            lawyer=lawyer, site_name="test", account="user",
            login_success_count=3, login_failure_count=1,
        )
        assert cred.success_rate == pytest.approx(0.75)


# =====================================================================
# CaseParty / CaseAssignment / CaseAccessGrant 约束
# =====================================================================


class TestCasePartyConstraints:
    """CaseParty、CaseAssignment、CaseAccessGrant 的唯一约束。"""

    @pytest.mark.django_db
    def test_case_party_unique(self) -> None:
        case = CaseFactory()
        client = ClientFactory()
        CaseParty.objects.create(case=case, client=client, legal_status="plaintiff")
        with pytest.raises(IntegrityError):
            CaseParty.objects.create(case=case, client=client, legal_status="defendant")

    @pytest.mark.django_db
    def test_case_assignment_unique(self) -> None:
        case = CaseFactory()
        lawyer = LawyerFactory()
        CaseAssignment.objects.create(case=case, lawyer=lawyer)
        with pytest.raises(IntegrityError):
            CaseAssignment.objects.create(case=case, lawyer=lawyer)

    @pytest.mark.django_db
    def test_case_access_grant_unique(self) -> None:
        case = CaseFactory()
        lawyer = LawyerFactory()
        CaseAccessGrant.objects.create(case=case, grantee=lawyer)
        with pytest.raises(IntegrityError):
            CaseAccessGrant.objects.create(case=case, grantee=lawyer)

    @pytest.mark.django_db
    def test_case_party_str(self) -> None:
        case = CaseFactory()
        client = ClientFactory()
        cp = CaseParty.objects.create(case=case, client=client, legal_status="plaintiff")
        result = str(cp)
        assert str(case.pk) in result
        assert str(client.pk) in result

    @pytest.mark.django_db
    def test_case_assignment_str(self) -> None:
        case = CaseFactory()
        lawyer = LawyerFactory()
        ca = CaseAssignment.objects.create(case=case, lawyer=lawyer)
        result = str(ca)
        assert str(case.pk) in result
        assert str(lawyer.pk) in result


# =====================================================================
# CaseFolderBinding 属性
# =====================================================================


class TestCaseFolderBinding:
    """CaseFolderBinding 的 folder_path_display 和 resolved_folder_path。"""

    @pytest.mark.django_db
    def test_folder_path_display_short(self) -> None:
        """短路径应完整显示。"""
        case = CaseFactory()
        binding = CaseFolderBinding(case=case, folder_path="/short/path")
        assert binding.folder_path_display == "/short/path"

    @pytest.mark.django_db
    def test_folder_path_display_empty(self) -> None:
        """空路径应返回空字符串。"""
        case = CaseFactory()
        binding = CaseFolderBinding(case=case, folder_path="")
        assert binding.folder_path_display == ""

    @pytest.mark.django_db
    def test_folder_path_display_truncation(self) -> None:
        """超过 50 字符的路径应被截断。"""
        case = CaseFactory()
        long_path = "/a" * 30  # 60 characters
        binding = CaseFolderBinding(case=case, folder_path=long_path)
        display = binding.folder_path_display
        assert "..." in display
        assert len(display) <= 53  # 23 + 3 + 24 + possible edge

    @pytest.mark.django_db
    def test_resolved_folder_path_fallback(self) -> None:
        """无 relative_path 时应返回 folder_path。"""
        case = CaseFactory()
        binding = CaseFolderBinding(case=case, folder_path="/fallback/path", relative_path="")
        assert binding.resolved_folder_path == "/fallback/path"


# =====================================================================
# CaseMaterialType __str__
# =====================================================================


class TestCaseMaterialType:
    """CaseMaterialType 的 __str__。"""

    @pytest.mark.django_db
    def test_str_without_law_firm(self) -> None:
        """无律所时应显示 '全局'。"""
        mtype = CaseMaterialType.objects.create(name="起诉状", category="party", law_firm=None)
        result = str(mtype)
        assert "全局" in result
        assert "起诉状" in result

    @pytest.mark.django_db
    def test_str_with_law_firm(self) -> None:
        from apps.organization.models import LawFirm
        firm = LawFirm.objects.create(name="测试律所")
        mtype = CaseMaterialType.objects.create(name="起诉状", category="party", law_firm=firm)
        result = str(mtype)
        assert "测试律所" in result


# =====================================================================
# SecretCodec 加密
# =====================================================================


class TestSecretCodec:
    """SecretCodec 的加密、解密、round-trip。"""

    def _make_codec(self) -> tuple[SecretCodec, str]:
        """创建带测试密钥的 codec，返回 (codec, key)。"""
        assert Fernet is not None, "cryptography 库未安装"
        key = Fernet.generate_key().decode()
        return SecretCodec(), key

    def test_encrypt_decrypt_round_trip(self) -> None:
        """加密后解密应返回原文。"""
        codec, key = self._make_codec()
        with patch.object(type(codec), "_get_cipher", return_value=Fernet(key.encode())):
            original = "my_secret_password_123"
            encrypted = codec.encrypt(original)
            decrypted = codec.decrypt(encrypted)
            assert decrypted == original

    def test_encrypt_output_has_prefix(self) -> None:
        codec, key = self._make_codec()
        with patch.object(type(codec), "_get_cipher", return_value=Fernet(key.encode())):
            encrypted = codec.encrypt("test")
            assert encrypted.startswith("enc:v1:")

    def test_is_encrypted_true(self) -> None:
        codec, key = self._make_codec()
        with patch.object(type(codec), "_get_cipher", return_value=Fernet(key.encode())):
            encrypted = codec.encrypt("test")
            assert codec.is_encrypted(encrypted) is True

    def test_is_encrypted_false_plaintext(self) -> None:
        codec, _ = self._make_codec()
        assert codec.is_encrypted("plaintext") is False

    def test_is_encrypted_false_none(self) -> None:
        codec, _ = self._make_codec()
        assert codec.is_encrypted(None) is False

    def test_is_encrypted_false_empty(self) -> None:
        codec, _ = self._make_codec()
        assert codec.is_encrypted("") is False

    def test_encrypt_idempotent(self) -> None:
        """已加密的值再次加密应原样返回。"""
        codec, key = self._make_codec()
        with patch.object(type(codec), "_get_cipher", return_value=Fernet(key.encode())):
            encrypted = codec.encrypt("test")
            double_encrypted = codec.encrypt(encrypted)
            assert double_encrypted == encrypted

    def test_decrypt_passthrough_plaintext(self) -> None:
        """未加密的值解密应原样返回。"""
        codec, _ = self._make_codec()
        assert codec.decrypt("plaintext") == "plaintext"

    def test_try_decrypt_success(self) -> None:
        codec, key = self._make_codec()
        with patch.object(type(codec), "_get_cipher", return_value=Fernet(key.encode())):
            encrypted = codec.encrypt("secret")
            assert codec.try_decrypt(encrypted) == "secret"

    def test_try_decrypt_invalid_token_debug_fallback(self) -> None:
        """DEBUG 模式下解密失败应返回原值。"""
        codec, _ = self._make_codec()
        with patch("apps.core.security.secret_codec.settings") as mock_settings:
            mock_settings.DEBUG = True
            result = codec.try_decrypt("enc:v1:invalid_base64_data")
            assert result == "enc:v1:invalid_base64_data"
