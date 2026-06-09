"""Comprehensive model tests for cases app - Chat, Log, Material, Party models."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.cases.models import (
    Case,
    CaseAccessGrant,
    CaseAssignment,
    CaseChat,
    CaseFolderBinding,
    CaseLog,
    CaseLogAttachment,
    CaseLogVersion,
    CaseMaterial,
    CaseMaterialCategory,
    CaseMaterialGroupOrder,
    CaseMaterialSide,
    CaseMaterialType,
    CaseNumber,
    CaseParty,
    ChatAuditLog,
    SupervisingAuthority,
)
from apps.contracts.models import Contract
from apps.organization.models import Lawyer
from apps.client.models import Client


# ── CaseChat Model ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCaseChatModelExtended:
    """CaseChat extended method tests."""

    def _make_chat(self, **kwargs: Any) -> CaseChat:
        contract = Contract.objects.create(name="chat合同", case_type="civil")
        case = Case.objects.create(name="chat案件", contract=contract)
        defaults = {"case": case, "chat_id": "chat_001", "name": "测试群聊"}
        defaults.update(kwargs)
        return CaseChat.objects.create(**defaults)

    def test_str_representation(self) -> None:
        chat = self._make_chat(platform="feishu")
        result = str(chat)
        assert "测试群聊" in result

    def test_get_owner_display_no_owner(self) -> None:
        chat = self._make_chat()
        assert chat.get_owner_display() == "未设置群主"

    def test_get_owner_display_unverified(self) -> None:
        chat = self._make_chat(owner_id="owner_001", owner_verified=False)
        result = chat.get_owner_display()
        assert "owner_001" in result
        assert "未验证" in result

    def test_get_owner_display_verified(self) -> None:
        chat = self._make_chat(owner_id="owner_001", owner_verified=True)
        result = chat.get_owner_display()
        assert "owner_001" in result
        assert "已验证" in result

    def test_is_owner_verified_recently_not_verified(self) -> None:
        chat = self._make_chat(owner_verified=False)
        assert chat.is_owner_verified_recently() is False

    def test_is_owner_verified_recently_no_time(self) -> None:
        chat = self._make_chat(owner_verified=True, owner_verified_at=None)
        assert chat.is_owner_verified_recently() is False

    def test_is_owner_verified_recently_within_hours(self) -> None:
        chat = self._make_chat(
            owner_verified=True,
            owner_verified_at=timezone.now() - timedelta(hours=1),
        )
        assert chat.is_owner_verified_recently(hours=24) is True

    def test_is_owner_verified_recently_expired(self) -> None:
        chat = self._make_chat(
            owner_verified=True,
            owner_verified_at=timezone.now() - timedelta(hours=48),
        )
        assert chat.is_owner_verified_recently(hours=24) is False

    def test_get_creation_summary_basic(self) -> None:
        chat = self._make_chat()
        summary = chat.get_creation_summary()
        assert "测试群聊" in summary

    def test_get_creation_summary_with_owner(self) -> None:
        chat = self._make_chat(owner_id="owner_001", owner_verified=True)
        summary = chat.get_creation_summary()
        assert "owner_001" in summary
        assert "已验证" in summary


# ── ChatAuditLog Model ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestChatAuditLogModel:
    """ChatAuditLog model tests."""

    def _make_audit_log(self, **kwargs: Any) -> ChatAuditLog:
        contract = Contract.objects.create(name="audit合同", case_type="civil")
        case = Case.objects.create(name="audit案件", contract=contract)
        chat = CaseChat.objects.create(case=case, chat_id="audit_chat_001", name="审计群聊")
        defaults: dict[str, Any] = {
            "chat": chat,
            "case": case,
            "action": "CREATE_SUCCESS",
            "details": {"key": "value"},
            "success": True,
        }
        defaults.update(kwargs)
        return ChatAuditLog.objects.create(**defaults)

    def test_str_with_external_chat_id(self) -> None:
        log = self._make_audit_log(external_chat_id="ext_123")
        result = str(log)
        assert "ext_123" in result
        assert "SUCCESS" in result

    def test_str_without_external_chat_id(self) -> None:
        log = self._make_audit_log(external_chat_id="")
        result = str(log)
        assert "ChatModel:" in result or "SUCCESS" in result

    def test_str_failed_action(self) -> None:
        log = self._make_audit_log(success=False)
        result = str(log)
        assert "FAILED" in result

    def test_formatted_details_json(self) -> None:
        log = self._make_audit_log(details={"nested": {"key": "val"}})
        result = log.formatted_details
        assert "nested" in result

    def test_formatted_details_non_serializable(self) -> None:
        log = self._make_audit_log()
        log.details = object()  # non-serializable
        result = log.formatted_details
        assert isinstance(result, str)

    def test_summary_basic(self) -> None:
        log = self._make_audit_log()
        summary = log.summary
        assert "创建成功" in summary

    def test_summary_with_error(self) -> None:
        log = self._make_audit_log(success=False, error_message="Something went wrong")
        summary = log.summary
        assert "错误" in summary

    def test_summary_truncates_long_error(self) -> None:
        log = self._make_audit_log(
            success=False,
            error_message="A" * 200,
        )
        summary = log.summary
        assert "错误:" in summary

    def test_summary_with_external_chat_id(self) -> None:
        log = self._make_audit_log(external_chat_id="ext_chat")
        summary = log.summary
        assert "ext_chat" in summary


# ── CaseLog Model ────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCaseLogModelExtended:
    """CaseLog extended properties tests."""

    def _make_log(self, **kwargs: Any) -> CaseLog:
        contract = Contract.objects.create(name="log合同", case_type="civil")
        case = Case.objects.create(name="log案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="log_actor", real_name="日志律师")
        defaults: dict[str, Any] = {"case": case, "actor": lawyer, "content": "测试日志"}
        defaults.update(kwargs)
        return CaseLog.objects.create(**defaults)

    def test_str(self) -> None:
        contract = Contract.objects.create(name="str_log合同", case_type="civil")
        case = Case.objects.create(name="str_log案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="str_actor", real_name="律师")
        log = CaseLog.objects.create(case=case, actor=lawyer, content="测试")
        result = str(log)
        assert str(case.id) in result

    def test_reminder_entries_no_id(self) -> None:
        """Unsaved log returns empty list."""
        log = CaseLog(content="test")
        assert log.reminder_entries == []

    def test_has_reminders_no_id(self) -> None:
        log = CaseLog(content="test")
        assert log.has_reminders is False

    def test_reminder_count_no_id(self) -> None:
        log = CaseLog(content="test")
        assert log.reminder_count == 0

    @patch("apps.core.interfaces.ServiceLocator")
    def test_reminder_entries_with_service(self, mock_locator: Any) -> None:
        contract = Contract.objects.create(name="rem_log合同", case_type="civil")
        case = Case.objects.create(name="rem_log案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="rem_actor", real_name="律师")
        log = CaseLog.objects.create(case=case, actor=lawyer, content="提醒测试")
        mock_svc = MagicMock()
        mock_svc.export_case_log_reminders_internal.return_value = [
            {"reminder_type": "court_date", "due_at": "2026-06-01T10:00:00"}
        ]
        mock_locator.get_reminder_service.return_value = mock_svc
        entries = log.reminder_entries
        assert len(entries) == 1

    @patch("apps.core.interfaces.ServiceLocator")
    def test_has_reminders_true(self, mock_locator: Any) -> None:
        contract = Contract.objects.create(name="has_rem合同", case_type="civil")
        case = Case.objects.create(name="has_rem案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="has_rem_actor", real_name="律师")
        log = CaseLog.objects.create(case=case, actor=lawyer, content="有提醒")
        mock_svc = MagicMock()
        mock_svc.export_case_log_reminders_internal.return_value = [{"type": "x"}]
        mock_locator.get_reminder_service.return_value = mock_svc
        assert log.has_reminders is True

    @patch("apps.core.interfaces.ServiceLocator")
    def test_reminder_count_value(self, mock_locator: Any) -> None:
        contract = Contract.objects.create(name="count_rem合同", case_type="civil")
        case = Case.objects.create(name="count_rem案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="count_rem_actor", real_name="律师")
        log = CaseLog.objects.create(case=case, actor=lawyer, content="计数提醒")
        mock_svc = MagicMock()
        mock_svc.export_case_log_reminders_internal.return_value = [{"a": 1}, {"b": 2}]
        mock_locator.get_reminder_service.return_value = mock_svc
        assert log.reminder_count == 2

    def test_latest_reminder_no_id(self) -> None:
        log = CaseLog(content="test")
        assert log._latest_reminder is None

    def test_reminder_type_no_reminder(self) -> None:
        log = CaseLog(content="test")
        assert log.reminder_type is None

    def test_reminder_time_no_reminder(self) -> None:
        log = CaseLog(content="test")
        assert log.reminder_time is None


# ── CaseLogAttachment Model ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestCaseLogAttachmentModel:
    """CaseLogAttachment model tests."""

    def test_save_sets_original_filename(self) -> None:
        contract = Contract.objects.create(name="att合同", case_type="civil")
        case = Case.objects.create(name="att案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="att_actor", real_name="律师")
        log = CaseLog.objects.create(case=case, actor=lawyer, content="附件日志")
        att = CaseLogAttachment(log=log)
        # Simulate file.name without actually storing
        att.file.name = "2024/01/test_file.pdf"
        att.save()
        assert att.original_filename == "test_file.pdf"

    def test_save_preserves_existing_filename(self) -> None:
        contract = Contract.objects.create(name="att2合同", case_type="civil")
        case = Case.objects.create(name="att2案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="att2_actor", real_name="律师")
        log = CaseLog.objects.create(case=case, actor=lawyer, content="附件日志2")
        att = CaseLogAttachment(log=log, original_filename="existing_name.pdf")
        att.file.name = "2024/01/other.pdf"
        att.save()
        assert att.original_filename == "existing_name.pdf"


# ── CaseLogVersion Model ────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCaseLogVersionModel:
    """CaseLogVersion model tests."""

    def test_str(self) -> None:
        contract = Contract.objects.create(name="ver合同", case_type="civil")
        case = Case.objects.create(name="ver案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="ver_actor", real_name="律师")
        log = CaseLog.objects.create(case=case, actor=lawyer, content="版本日志")
        version = CaseLogVersion.objects.create(
            log=log, content="旧内容", actor=lawyer
        )
        result = str(version)
        assert str(log.id) in result


# ── CaseNumber Model ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCaseNumberModelExtended:
    """CaseNumber model tests."""

    def test_get_full_number_with_document(self) -> None:
        contract = Contract.objects.create(name="num_doc合同", case_type="civil")
        case = Case.objects.create(name="num_doc案件", contract=contract)
        cn = CaseNumber.objects.create(
            case=case,
            number="(2024)京01民初1号",
            document_name="民事判决书",
        )
        result = cn.get_full_number()
        assert "民事判决书" in result
        assert "京01民初1号" in result

    def test_get_full_number_without_document(self) -> None:
        contract = Contract.objects.create(name="num_nodoc合同", case_type="civil")
        case = Case.objects.create(name="num_nodoc案件", contract=contract)
        cn = CaseNumber.objects.create(
            case=case,
            number="(2024)京01民初1号",
        )
        result = cn.get_full_number()
        assert result == "(2024)京01民初1号"


# ── SupervisingAuthority Model ──────────────────────────────────────────────


@pytest.mark.django_db
class TestSupervisingAuthorityModelExtended:
    """SupervisingAuthority __str__ variants."""

    def _make_case(self) -> Case:
        contract = Contract.objects.create(name="auth合同", case_type="civil")
        return Case.objects.create(name="auth案件", contract=contract)

    def test_str_with_name_and_type(self) -> None:
        case = self._make_case()
        auth = SupervisingAuthority.objects.create(
            case=case, name="北京法院", authority_type="trial"
        )
        result = str(auth)
        assert "北京法院" in result

    def test_str_with_name_only(self) -> None:
        case = self._make_case()
        auth = SupervisingAuthority.objects.create(case=case, name="某法院")
        result = str(auth)
        assert "某法院" in result

    def test_str_with_type_only(self) -> None:
        case = self._make_case()
        auth = SupervisingAuthority.objects.create(case=case, authority_type="trial")
        result = str(auth)
        assert "审理机构" in result

    def test_str_with_neither(self) -> None:
        case = self._make_case()
        auth = SupervisingAuthority.objects.create(case=case)
        result = str(auth)
        assert "审理机构" in result or "主管机关" in result or str(auth.id) in result


# ── Case Model Extended ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCaseModelExtended:
    """Case model extended tests."""

    def test_get_case_chain_single(self) -> None:
        contract = Contract.objects.create(name="chain合同", case_type="civil")
        case = Case.objects.create(name="一审案件", contract=contract)
        chain = case.get_case_chain()
        assert len(chain) == 1
        assert chain[0] == case

    def test_get_case_chain_two_levels(self) -> None:
        contract = Contract.objects.create(name="chain2合同", case_type="civil")
        case1 = Case.objects.create(name="一审", contract=contract)
        case2 = Case.objects.create(name="二审", contract=contract, previous_case=case1)
        chain = case2.get_case_chain()
        assert len(chain) == 2
        assert chain[0] == case1
        assert chain[1] == case2

    def test_get_case_chain_three_levels(self) -> None:
        contract = Contract.objects.create(name="chain3合同", case_type="civil")
        case1 = Case.objects.create(name="一审", contract=contract)
        case2 = Case.objects.create(name="二审", contract=contract, previous_case=case1)
        case3 = Case.objects.create(name="再审", contract=contract, previous_case=case2)
        chain = case3.get_case_chain()
        assert len(chain) == 3
        assert chain[0] == case1
        assert chain[2] == case3

    def test_clean_valid_stage(self) -> None:
        contract = Contract.objects.create(name="clean合同", case_type="civil")
        case = Case(
            name="clean案件",
            contract=contract,
            current_stage="first_trial",
        )
        case.clean()  # Should not raise

    def test_clean_invalid_stage_raises(self) -> None:
        contract = Contract.objects.create(name="clean_invalid合同", case_type="civil")
        case = Case(
            name="clean_invalid案件",
            contract=contract,
            current_stage="completely_invalid_stage_xyz",
        )
        with pytest.raises(ValidationError):
            case.clean()

    def test_clean_no_stage(self) -> None:
        contract = Contract.objects.create(name="clean_none合同", case_type="civil")
        case = Case(name="clean_none案件", contract=contract, current_stage=None)
        case.clean()  # Should not raise


# ── Material Models ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCaseMaterialTypeModel:
    """CaseMaterialType model tests."""

    def test_str_global_scope(self) -> None:
        mtype = CaseMaterialType.objects.create(
            category=CaseMaterialCategory.PARTY,
            name="身份证",
        )
        result = str(mtype)
        assert "全局" in result
        assert "当事人材料" in result
        assert "身份证" in result

    def test_str_with_law_firm(self) -> None:
        from apps.organization.models import LawFirm

        firm = LawFirm.objects.create(name="测试律所")
        mtype = CaseMaterialType.objects.create(
            category=CaseMaterialCategory.NON_PARTY,
            name="公证书",
            law_firm=firm,
        )
        result = str(mtype)
        assert "测试律所" in result
        assert "非当事人材料" in result


@pytest.mark.django_db
class TestCaseMaterialModel:
    """CaseMaterial model tests."""

    def test_str(self) -> None:
        contract = Contract.objects.create(name="mat合同", case_type="civil")
        case = Case.objects.create(name="mat案件", contract=contract)
        mat = CaseMaterial.objects.create(
            case=case,
            category=CaseMaterialCategory.PARTY,
            type_name="身份证",
        )
        result = str(mat)
        assert str(case.id) in result
        assert "身份证" in result


@pytest.mark.django_db
class TestCaseMaterialGroupOrderModel:
    """CaseMaterialGroupOrder model tests."""

    def test_str(self) -> None:
        contract = Contract.objects.create(name="grp合同", case_type="civil")
        case = Case.objects.create(name="grp案件", contract=contract)
        mtype = CaseMaterialType.objects.create(
            category=CaseMaterialCategory.PARTY,
            name="营业执照",
        )
        order = CaseMaterialGroupOrder.objects.create(
            case=case,
            category=CaseMaterialCategory.PARTY,
            type=mtype,
            sort_index=3,
        )
        result = str(order)
        assert str(case.id) in result
        assert "3" in result


# ── CaseFolderBinding Model ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestCaseFolderBindingModel:
    """CaseFolderBinding model tests."""

    def test_str(self) -> None:
        contract = Contract.objects.create(name="folder合同", case_type="civil")
        case = Case.objects.create(name="folder案件", contract=contract)
        binding = CaseFolderBinding.objects.create(
            case=case, folder_path="/data/cases/folder案件"
        )
        result = str(binding)
        assert "folder案件" in result

    def test_resolved_folder_path_no_relative(self) -> None:
        contract = Contract.objects.create(name="resolved合同", case_type="civil")
        case = Case.objects.create(name="resolved案件", contract=contract)
        binding = CaseFolderBinding.objects.create(
            case=case, folder_path="/data/folder"
        )
        assert binding.resolved_folder_path == "/data/folder"

    def test_resolved_folder_path_with_relative(self) -> None:
        from apps.contracts.models import ContractFolderBinding as CFB

        contract = Contract.objects.create(name="resolved_rel合同", case_type="civil")
        CFB.objects.create(contract=contract, folder_path="/contracts/main")
        case = Case.objects.create(name="resolved_rel案件", contract=contract)
        binding = CaseFolderBinding.objects.create(
            case=case,
            folder_path="/fallback",
            relative_path="2026.01.01-案件",
        )
        result = binding.resolved_folder_path
        assert "2026.01.01-案件" in result

    def test_folder_path_display_short(self) -> None:
        contract = Contract.objects.create(name="short合同", case_type="civil")
        case = Case.objects.create(name="short案件", contract=contract)
        binding = CaseFolderBinding.objects.create(
            case=case, folder_path="/short"
        )
        assert binding.folder_path_display == "/short"

    def test_folder_path_display_long_truncated(self) -> None:
        contract = Contract.objects.create(name="long合同", case_type="civil")
        case = Case.objects.create(name="long案件", contract=contract)
        long_path = "/data/" + "a" * 100
        binding = CaseFolderBinding.objects.create(
            case=case, folder_path=long_path
        )
        result = binding.folder_path_display
        assert "..." in result
        assert len(result) <= 50

    def test_resolved_folder_path_no_contract(self) -> None:
        """Case with no contract falls back to folder_path."""
        case = Case.objects.create(name="no_contract案件", contract=None)
        binding = CaseFolderBinding.objects.create(
            case=case, folder_path="/fallback"
        )
        assert binding.resolved_folder_path == "/fallback"


# ── CaseParty / CaseAssignment / CaseAccessGrant ────────────────────────────


@pytest.mark.django_db
class TestCasePartyModelExtended:
    """CaseParty model tests."""

    def test_str(self) -> None:
        contract = Contract.objects.create(name="party_str合同", case_type="civil")
        case = Case.objects.create(name="party_str案件", contract=contract)
        client = Client.objects.create(name="当事人A", client_type="natural")
        party = CaseParty.objects.create(
            case=case, client=client, legal_status="plaintiff"
        )
        result = str(party)
        assert str(case.id) in result
        assert str(client.id) in result


@pytest.mark.django_db
class TestCaseAccessGrantModel:
    """CaseAccessGrant model tests."""

    def test_str(self) -> None:
        contract = Contract.objects.create(name="grant合同", case_type="civil")
        case = Case.objects.create(name="grant案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="grantee", real_name="授权律师")
        grant = CaseAccessGrant.objects.create(case=case, grantee=lawyer)
        result = str(grant)
        assert str(case.id) in result
        assert str(lawyer.id) in result


# ── CaseFilingNumberSequence ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestCaseFilingNumberSequence:
    """CaseFilingNumberSequence model tests."""

    def test_create_sequence(self) -> None:
        from apps.cases.models import CaseFilingNumberSequence

        seq = CaseFilingNumberSequence.objects.create(year=2026, next_value=5)
        assert seq.year == 2026
        assert seq.next_value == 5

    def test_unique_year(self) -> None:
        from apps.cases.models import CaseFilingNumberSequence

        CaseFilingNumberSequence.objects.create(year=2025)
        with pytest.raises(Exception):
            CaseFilingNumberSequence.objects.create(year=2025)


# ── Template binding model ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestCaseTemplateBindingModel:
    """CaseTemplateBinding model tests."""

    def test_binding_source_choices(self) -> None:
        from apps.cases.models import BindingSource

        assert BindingSource.AUTO_RECOMMENDED == "auto_recommended"
        assert BindingSource.MANUAL_BOUND == "manual_bound"


# ── Validate Log Attachment ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestValidateLogAttachmentFunction:
    """validate_log_attachment model validator tests."""

    def test_valid_file_passes(self) -> None:
        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        mock_file.size = 1024
        # Should not raise
        from apps.cases.models.log import validate_log_attachment

        validate_log_attachment(mock_file)

    def test_invalid_extension_raises(self) -> None:
        mock_file = MagicMock()
        mock_file.name = "test.exe"
        mock_file.size = 1024
        from apps.cases.models.log import validate_log_attachment

        with pytest.raises(ValidationError, match="不支持"):
            validate_log_attachment(mock_file)
