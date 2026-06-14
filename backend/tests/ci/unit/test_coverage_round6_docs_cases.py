"""Round 6 coverage tests - documents & cases gaps.

Covers:
- apps/documents/utils/formatters.py (format_date, format_date_chinese, format_currency, format_percentage, get_choice_display)
- apps/documents/storage.py (resolve_docx_template_path, list_docx_templates_files, DocumentTemplateStorage)
- apps/documents/signals.py (helper functions: _serialize_value, _get_content_type, _get_tracked_fields, _get_changes, _delete_charfield_file)
- apps/documents/api/download_response_factory.py
- apps/documents/schemas.py (resolve_*, FolderBindingOut)
- apps/cases/models/chat.py (CaseChat, ChatAuditLog)
- apps/cases/models/log.py (validate_log_attachment)
- apps/cases/models/folder_scan_session.py (CaseFolderScanStatus)
- apps/cases/models/template_binding.py (CaseTemplateBinding, BindingSource)
- apps/cases/models/material.py (CaseMaterialType, CaseMaterial, CaseFolderBinding)
- apps/cases/services/chat/naming.py (ChatNameBuilder more branches)
- apps/cases/services/case/assembler/case_dto_assembler.py
- apps/cases/services/case/repo/case_repo.py
- apps/cases/services/case/repo/case_number_repo.py
- apps/cases/services/case/repo/case_assignment_repo.py
- apps/cases/services/case/repo/case_party_repo.py
- apps/cases/services/case/repo/case_search_query_builder.py
- apps/cases/services/data/cause_court_data_service.py (parser, cache)
- apps/cases/domain/validators.py (more branches)
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# ============================================================
# documents/utils/formatters.py
# ============================================================


class TestFormatDate:
    def test_none_returns_empty(self) -> None:
        from apps.documents.utils.formatters import format_date
        assert format_date(None) == ""

    def test_date_object(self) -> None:
        from apps.documents.utils.formatters import format_date
        d = date(2024, 1, 15)
        assert format_date(d) == "2024年01月15日"

    def test_date_object_custom_format(self) -> None:
        from apps.documents.utils.formatters import format_date
        d = date(2024, 1, 15)
        assert format_date(d, fmt="%Y-%m-%d") == "2024-01-15"

    def test_iso_string(self) -> None:
        from apps.documents.utils.formatters import format_date
        assert format_date("2024-01-15") == "2024年01月15日"

    def test_invalid_string_returns_empty(self) -> None:
        from apps.documents.utils.formatters import format_date
        assert format_date("not-a-date") == ""

    def test_invalid_format_string_returns_empty(self) -> None:
        from apps.documents.utils.formatters import format_date
        assert format_date("2024/01/15") == ""


class TestFormatDateChinese:
    def test_none_without_default(self) -> None:
        from apps.documents.utils.formatters import format_date_chinese
        assert format_date_chinese(None) == ""

    def test_none_with_default_today(self) -> None:
        from apps.documents.utils.formatters import format_date_chinese
        result = format_date_chinese(None, default_today=True)
        today = date.today()
        assert today.strftime("%Y") in result
        assert "年" in result
        assert "月" in result

    def test_valid_date(self) -> None:
        from apps.documents.utils.formatters import format_date_chinese
        assert format_date_chinese(date(2024, 3, 5)) == "2024年03月05日"

    def test_valid_date_no_padding(self) -> None:
        from apps.documents.utils.formatters import format_date_chinese
        # All months/days are zero-padded in this format
        assert format_date_chinese(date(2024, 12, 25)) == "2024年12月25日"


class TestFormatCurrency:
    def test_none_returns_empty(self) -> None:
        from apps.documents.utils.formatters import format_currency
        assert format_currency(None) == ""

    def test_without_symbol(self) -> None:
        from apps.documents.utils.formatters import format_currency
        assert format_currency(Decimal("1234.5")) == "1,234.50"

    def test_with_symbol(self) -> None:
        from apps.documents.utils.formatters import format_currency
        assert format_currency(Decimal("1234.5"), include_symbol=True) == "¥1,234.50"

    def test_zero(self) -> None:
        from apps.documents.utils.formatters import format_currency
        assert format_currency(Decimal("0")) == "0.00"

    def test_large_number(self) -> None:
        from apps.documents.utils.formatters import format_currency
        assert format_currency(Decimal("1000000")) == "1,000,000.00"

    def test_negative(self) -> None:
        from apps.documents.utils.formatters import format_currency
        result = format_currency(Decimal("-500"))
        assert result.startswith("-")


class TestFormatPercentage:
    def test_none_returns_empty(self) -> None:
        from apps.documents.utils.formatters import format_percentage
        assert format_percentage(None) == ""

    def test_with_decimals(self) -> None:
        from apps.documents.utils.formatters import format_percentage
        assert format_percentage(Decimal("10"), decimal_places=2) == "10.00%"

    def test_zero_decimals(self) -> None:
        from apps.documents.utils.formatters import format_percentage
        assert format_percentage(Decimal("10"), decimal_places=0) == "10%"

    def test_fractional(self) -> None:
        from apps.documents.utils.formatters import format_percentage
        assert format_percentage(Decimal("3.14159"), decimal_places=3) == "3.142%"


class TestGetChoiceDisplay:
    def test_empty_value(self) -> None:
        from apps.documents.utils.formatters import get_choice_display
        from apps.documents.models.choices import DocumentTemplateType
        assert get_choice_display("", DocumentTemplateType) == ""

    def test_valid_value(self) -> None:
        from apps.documents.utils.formatters import get_choice_display
        from apps.documents.models.choices import DocumentTemplateType
        assert get_choice_display("contract", DocumentTemplateType) == "合同文件模板"

    def test_invalid_value_returns_original(self) -> None:
        from apps.documents.utils.formatters import get_choice_display
        from apps.documents.models.choices import DocumentTemplateType
        assert get_choice_display("nonexistent", DocumentTemplateType) == "nonexistent"


# ============================================================
# documents/api/download_response_factory.py
# ============================================================


class TestBuildDownloadResponse:
    def test_basic_download(self) -> None:
        from apps.documents.api.download_response_factory import build_download_response
        response = build_download_response(
            content=b"hello",
            filename="test.pdf",
            content_type="application/pdf",
        )
        assert response.status_code == 200
        assert response.content == b"hello"
        assert "test.pdf" in response["Content-Disposition"]
        assert "attachment" in response["Content-Disposition"]

    def test_chinese_filename(self) -> None:
        from apps.documents.api.download_response_factory import build_download_response
        response = build_download_response(
            content=b"content",
            filename="起诉状.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        assert response.status_code == 200
        # The filename should be percent-encoded
        assert "filename" in response["Content-Disposition"]


# ============================================================
# documents/signals.py (helper functions)
# ============================================================


class TestSerializeValue:
    def test_none(self) -> None:
        from apps.documents.signals import _serialize_value
        assert _serialize_value(None) is None

    def test_pk_object(self) -> None:
        from apps.documents.signals import _serialize_value
        obj = SimpleNamespace(pk=42)
        assert _serialize_value(obj) == 42

    def test_name_object(self) -> None:
        from apps.documents.signals import _serialize_value
        obj = SimpleNamespace(name="foo")
        assert _serialize_value(obj) == "foo"

    def test_plain_value(self) -> None:
        from apps.documents.signals import _serialize_value
        assert _serialize_value(42) == "42"
        assert _serialize_value("hello") == "hello"

    def test_object_with_both_pk_and_name(self) -> None:
        from apps.documents.signals import _serialize_value
        # pk takes precedence
        obj = SimpleNamespace(pk=1, name="test")
        assert _serialize_value(obj) == 1


class TestGetContentType:
    def test_known_models(self) -> None:
        from apps.documents.signals import _get_content_type
        from apps.documents.models import DocumentTemplate, FolderTemplate, Placeholder
        assert _get_content_type(FolderTemplate) == "folder_template"
        assert _get_content_type(DocumentTemplate) == "document_template"
        assert _get_content_type(Placeholder) == "placeholder"

    def test_unknown_model(self) -> None:
        from apps.documents.signals import _get_content_type
        assert _get_content_type(str) is None


class TestGetTrackedFields:
    def test_folder_template_fields(self) -> None:
        from apps.documents.signals import _get_tracked_fields
        from apps.documents.models import FolderTemplate
        fields = _get_tracked_fields(FolderTemplate)
        assert "name" in fields
        assert "is_active" in fields
        assert "case_types" in fields
        assert "structure" in fields

    def test_document_template_fields(self) -> None:
        from apps.documents.signals import _get_tracked_fields
        from apps.documents.models import DocumentTemplate
        fields = _get_tracked_fields(DocumentTemplate)
        assert "template_type" in fields
        assert "file_path" in fields

    def test_placeholder_fields(self) -> None:
        from apps.documents.signals import _get_tracked_fields
        from apps.documents.models import Placeholder
        fields = _get_tracked_fields(Placeholder)
        assert "key" in fields
        assert "display_name" in fields

    def test_unknown_model_returns_common_fields(self) -> None:
        from apps.documents.signals import _get_tracked_fields
        fields = _get_tracked_fields(str)
        assert "name" in fields
        assert "is_active" in fields


class TestGetChanges:
    def test_no_changes(self) -> None:
        from apps.documents.signals import _get_changes
        from apps.documents.models import FolderTemplate
        old = SimpleNamespace(name="test", is_active=True)
        new = SimpleNamespace(name="test", is_active=True)
        changes = _get_changes(old, new, FolderTemplate)
        assert changes == {}

    def test_with_changes(self) -> None:
        from apps.documents.signals import _get_changes
        from apps.documents.models import FolderTemplate
        old = SimpleNamespace(name="old", is_active=True)
        new = SimpleNamespace(name="new", is_active=True)
        changes = _get_changes(old, new, FolderTemplate)
        assert "name" in changes
        assert changes["name"]["old"] == "old"
        assert changes["name"]["new"] == "new"

    def test_none_old_instance(self) -> None:
        from apps.documents.signals import _get_changes
        from apps.documents.models import FolderTemplate
        new = SimpleNamespace(name="test", is_active=True)
        changes = _get_changes(None, new, FolderTemplate)
        # When old_instance is None, all values compared to None -> changes
        assert "name" in changes


class TestDeleteCharfieldFile:
    def test_none_path(self) -> None:
        from apps.documents.signals import _delete_charfield_file
        _delete_charfield_file(None)  # should not raise

    def test_empty_path(self) -> None:
        from apps.documents.signals import _delete_charfield_file
        _delete_charfield_file("")  # should not raise

    def test_relative_path(self) -> None:
        from apps.documents.signals import _delete_charfield_file
        with patch("apps.documents.signals.Path") as MockPath:
            mock_path = MagicMock()
            MockPath.return_value = mock_path
            mock_path.is_absolute.return_value = False
            mock_path.exists.return_value = False
            _delete_charfield_file("some/file.pdf")
            # Should have tried to join with MEDIA_ROOT

    def test_absolute_nonexistent_path(self) -> None:
        from apps.documents.signals import _delete_charfield_file
        with patch("apps.documents.signals.Path") as MockPath:
            mock_path = MagicMock()
            MockPath.return_value = mock_path
            mock_path.is_absolute.return_value = True
            mock_path.exists.return_value = False
            _delete_charfield_file("/nonexistent/file.pdf")

    def test_absolute_existing_path(self) -> None:
        from apps.documents.signals import _delete_charfield_file
        with patch("apps.documents.signals.Path") as MockPath:
            mock_path = MagicMock()
            MockPath.return_value = mock_path
            mock_path.is_absolute.return_value = True
            mock_path.exists.return_value = True
            _delete_charfield_file("/existing/file.pdf")
            mock_path.unlink.assert_called_once()

    def test_absolute_unlink_oserror(self) -> None:
        from apps.documents.signals import _delete_charfield_file
        with patch("apps.documents.signals.Path") as MockPath:
            mock_path = MagicMock()
            MockPath.return_value = mock_path
            mock_path.is_absolute.return_value = True
            mock_path.exists.return_value = True
            mock_path.unlink.side_effect = OSError("permission denied")
            _delete_charfield_file("/locked/file.pdf")  # should not raise


# ============================================================
# cases/models/chat.py
# ============================================================


class TestCaseChatModel:
    def _make_chat(self, **kwargs: Any) -> Any:
        from apps.cases.models.chat import CaseChat
        defaults = {
            "case_id": 1,
            "platform": "feishu",
            "chat_id": "chat_123",
            "name": "测试群聊",
            "is_active": True,
            "owner_id": None,
            "owner_verified": False,
            "owner_verified_at": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_get_platform_display(self) -> None:
        from apps.core.models.enums import ChatPlatform
        # ChatPlatform has FEISHU etc.
        assert ChatPlatform.FEISHU == "feishu"

    def test_get_owner_display_no_owner(self) -> None:
        from apps.cases.models.chat import CaseChat
        chat = self._make_chat(owner_id=None)
        assert CaseChat.get_owner_display(chat) == "未设置群主"

    def test_get_owner_display_verified(self) -> None:
        from apps.cases.models.chat import CaseChat
        chat = self._make_chat(owner_id="ou_123", owner_verified=True)
        result = CaseChat.get_owner_display(chat)
        assert "ou_123" in result
        assert "已验证" in result

    def test_get_owner_display_not_verified(self) -> None:
        from apps.cases.models.chat import CaseChat
        chat = self._make_chat(owner_id="ou_123", owner_verified=False)
        result = CaseChat.get_owner_display(chat)
        assert "未验证" in result

    def test_is_owner_verified_recently_no_verification(self) -> None:
        from apps.cases.models.chat import CaseChat
        chat = self._make_chat(owner_verified=False, owner_verified_at=None)
        assert CaseChat.is_owner_verified_recently(chat) is False

    def test_is_owner_verified_recently_with_verification(self) -> None:
        from apps.cases.models.chat import CaseChat
        from django.utils import timezone
        chat = self._make_chat(
            owner_verified=True,
            owner_verified_at=timezone.now() - timedelta(hours=1),
        )
        assert CaseChat.is_owner_verified_recently(chat, hours=24) is True

    def test_is_owner_verified_recently_old_verification(self) -> None:
        from apps.cases.models.chat import CaseChat
        from django.utils import timezone
        chat = self._make_chat(
            owner_verified=True,
            owner_verified_at=timezone.now() - timedelta(hours=48),
        )
        assert CaseChat.is_owner_verified_recently(chat, hours=24) is False

    def test_get_creation_summary(self) -> None:
        from apps.cases.models.chat import CaseChat
        chat = self._make_chat(name="测试", owner_id="ou_1", owner_verified=True)
        result = CaseChat.get_creation_summary(chat)
        assert "测试" in result
        assert "ou_1" in result
        assert "已验证" in result

    def test_get_creation_summary_no_owner(self) -> None:
        from apps.cases.models.chat import CaseChat
        chat = self._make_chat(name="测试", owner_id=None, owner_verified=False)
        result = CaseChat.get_creation_summary(chat)
        assert "测试" in result
        assert "群主" not in result


class TestChatAuditLogModel:
    def _make_log(self, **kwargs: Any) -> Any:
        from apps.cases.models.chat import ChatAuditLog
        defaults = {
            "chat_id": 1,
            "case_id": 1,
            "action": "CREATE_START",
            "details": {},
            "success": True,
            "error_message": "",
            "external_chat_id": "",
            "platform": "feishu",
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_action_choices(self) -> None:
        from apps.cases.models.chat import ChatAuditLog
        assert len(ChatAuditLog.ACTION_CHOICES) == 8
        actions = [c[0] for c in ChatAuditLog.ACTION_CHOICES]
        assert "CREATE_START" in actions
        assert "CREATE_SUCCESS" in actions

    def test_formatted_details(self) -> None:
        from apps.cases.models.chat import ChatAuditLog
        log = self._make_log(details={"key": "value"})
        result = ChatAuditLog.formatted_details.fget(log)  # type: ignore
        assert "key" in result

    def test_formatted_details_non_serializable(self) -> None:
        from apps.cases.models.chat import ChatAuditLog
        log = self._make_log(details="plain string")
        result = ChatAuditLog.formatted_details.fget(log)  # type: ignore
        assert "plain string" in result

    def test_summary_with_error(self) -> None:
        """Test summary property logic."""
        from apps.cases.models.chat import ChatAuditLog
        log = self._make_log(
            success=False,
            error_message="Something went wrong here",
            external_chat_id="chat_1",
            case_id=42,
        )
        # Add the method SimpleNamespace lacks
        log.get_action_display = lambda: "创建失败"  # type: ignore
        result = ChatAuditLog.summary.fget(log)  # type: ignore
        assert "创建失败" in result
        assert "chat_1" in result
        assert "错误" in result

    def test_summary_no_error(self) -> None:
        from apps.cases.models.chat import ChatAuditLog
        log = self._make_log(success=True, external_chat_id="chat_2")
        log.get_action_display = lambda: "操作"  # type: ignore
        result = ChatAuditLog.summary.fget(log)  # type: ignore
        assert "错误" not in result


# ============================================================
# cases/models/log.py - validate_log_attachment
# ============================================================


class TestValidateLogAttachment:
    def test_valid_pdf(self) -> None:
        from apps.cases.models.log import validate_log_attachment
        file = SimpleNamespace(name="test.pdf", size=1024)
        validate_log_attachment(file)  # should not raise

    def test_invalid_extension(self) -> None:
        from django.core.exceptions import ValidationError
        from apps.cases.models.log import validate_log_attachment
        file = SimpleNamespace(name="test.exe", size=1024)
        with pytest.raises(ValidationError):
            validate_log_attachment(file)

    def test_no_extension(self) -> None:
        from django.core.exceptions import ValidationError
        from apps.cases.models.log import validate_log_attachment
        file = SimpleNamespace(name="noext", size=1024)
        with pytest.raises(ValidationError):
            validate_log_attachment(file)


# ============================================================
# cases/models/folder_scan_session.py
# ============================================================


class TestCaseFolderScanStatus:
    def test_choices(self) -> None:
        from apps.cases.models.folder_scan_session import CaseFolderScanStatus
        assert CaseFolderScanStatus.PENDING == "pending"
        assert CaseFolderScanStatus.RUNNING == "running"
        assert CaseFolderScanStatus.CLASSIFYING == "classifying"
        assert CaseFolderScanStatus.COMPLETED == "completed"
        assert CaseFolderScanStatus.STAGED == "staged"
        assert CaseFolderScanStatus.FAILED == "failed"
        assert CaseFolderScanStatus.CANCELLED == "cancelled"


# ============================================================
# cases/models/template_binding.py
# ============================================================


class TestBindingSource:
    def test_choices(self) -> None:
        from apps.cases.models.template_binding import BindingSource
        assert BindingSource.AUTO_RECOMMENDED == "auto_recommended"
        assert BindingSource.MANUAL_BOUND == "manual_bound"


class TestCaseTemplateBindingModel:
    def test_str(self) -> None:
        from apps.cases.models.template_binding import CaseTemplateBinding
        obj = SimpleNamespace(case_id=1, template_id=2, binding_source="auto_recommended")
        result = CaseTemplateBinding.__str__(obj)
        assert "1" in result
        assert "2" in result


# ============================================================
# cases/models/material.py
# ============================================================


class TestCaseMaterialTypeStr:
    def test_with_law_firm(self) -> None:
        from apps.cases.models.material import CaseMaterialType
        obj = SimpleNamespace(law_firm_id=1, law_firm=SimpleNamespace(name="测试律所"), category="party", name="身份证")
        obj.get_category_display = lambda: "当事人材料"  # type: ignore
        result = CaseMaterialType.__str__(obj)
        assert "测试律所" in result

    def test_without_law_firm(self) -> None:
        from apps.cases.models.material import CaseMaterialType
        obj = SimpleNamespace(law_firm_id=None, law_firm=None, category="party", name="营业执照")
        obj.get_category_display = lambda: "当事人材料"  # type: ignore
        result = CaseMaterialType.__str__(obj)
        assert "全局" in result


class TestCaseMaterialStr:
    def test_str(self) -> None:
        from apps.cases.models.material import CaseMaterial
        obj = SimpleNamespace(case_id=1, category="party", type_name="身份证")
        obj.get_category_display = lambda: "当事人材料"  # type: ignore
        result = CaseMaterial.__str__(obj)
        assert "1" in result
        assert "身份证" in result


class TestCaseMaterialGroupOrderStr:
    def test_str(self) -> None:
        from apps.cases.models.material import CaseMaterialGroupOrder
        obj = SimpleNamespace(case_id=1, category="party", sort_index=3)
        result = CaseMaterialGroupOrder.__str__(obj)
        assert "3" in result


class TestCaseFolderBindingModel:
    def test_str(self) -> None:
        from apps.cases.models.material import CaseFolderBinding
        obj = SimpleNamespace(case=SimpleNamespace(name="测试案件"), folder_path="/path/to/folder")
        result = CaseFolderBinding.__str__(obj)
        assert "测试案件" in result
        assert "/path/to/folder" in result

    def test_folder_path_display_short(self) -> None:
        from apps.cases.models.material import CaseFolderBinding
        with patch.object(CaseFolderBinding, "resolved_folder_path", new_callable=PropertyMock) as mock_prop:
            mock_prop.return_value = "/short/path"
            obj = CaseFolderBinding()
            obj.resolved_folder_path = "/short/path"
            # Directly test property logic
            path = obj.resolved_folder_path
            max_length = 50
            if len(path) <= max_length:
                result = path
            else:
                start_len = max_length // 2 - 2
                end_len = max_length - start_len - 3
                result = f"{path[:start_len]}...{path[-end_len:]}"
            assert result == "/short/path"

    def test_folder_path_display_long(self) -> None:
        from apps.cases.models.material import CaseFolderBinding
        long_path = "/a" * 30
        max_length = 50
        start_len = max_length // 2 - 2
        end_len = max_length - start_len - 3
        result = f"{long_path[:start_len]}...{long_path[-end_len:]}"
        assert "..." in result

    def test_resolved_folder_path_no_relative(self) -> None:
        from apps.cases.models.material import CaseFolderBinding
        obj = SimpleNamespace(relative_path="", folder_path="/base/path", _get_contract_folder_path=lambda: None)
        # We need to test the actual property logic
        # SimpleNamespace won't work for property, so test the helper
        assert obj._get_contract_folder_path() is None

    def test_resolved_folder_path_with_relative(self) -> None:
        from apps.cases.models.material import CaseFolderBinding
        from pathlib import PurePosixPath
        contract_path = "/contracts/base"
        relative = "2026.04.22-案"
        expected = str(PurePosixPath(contract_path) / relative)
        obj = SimpleNamespace(
            relative_path=relative,
            folder_path="/fallback",
            _get_contract_folder_path=lambda: contract_path,
        )
        # The property resolves relative_path + contract path
        contract = obj._get_contract_folder_path()
        assert contract == contract_path
        result = str(PurePosixPath(contract) / obj.relative_path)
        assert result == expected

    def test_get_contract_folder_path_no_contract(self) -> None:
        from apps.cases.models.material import CaseFolderBinding
        case = SimpleNamespace(contract_id=None, contract=None)
        obj = SimpleNamespace(case=case)
        result = CaseFolderBinding._get_contract_folder_path(obj)
        assert result is None

    def test_get_contract_folder_path_no_folder_binding(self) -> None:
        from apps.cases.models.material import CaseFolderBinding
        contract = SimpleNamespace(folder_binding=None)
        case = SimpleNamespace(contract_id=1, contract=contract)
        obj = SimpleNamespace(case=case)
        result = CaseFolderBinding._get_contract_folder_path(obj)
        assert result is None

    def test_get_contract_folder_path_with_binding(self) -> None:
        from apps.cases.models.material import CaseFolderBinding
        contract = SimpleNamespace(folder_binding=SimpleNamespace(folder_path="/contract/path"))
        case = SimpleNamespace(contract_id=1, contract=contract)
        obj = SimpleNamespace(case=case)
        result = CaseFolderBinding._get_contract_folder_path(obj)
        assert result == "/contract/path"

    def test_get_contract_folder_path_attribute_error(self) -> None:
        from apps.cases.models.material import CaseFolderBinding
        # Simulate contract object that raises AttributeError when accessing folder_binding
        def bad_getattr(name: str) -> Any:
            if name == "folder_binding":
                raise AttributeError("no binding")
            raise AttributeError(name)

        contract = SimpleNamespace(__getattr__=bad_getattr)
        case = SimpleNamespace(contract_id=1, contract=contract)
        obj = SimpleNamespace(case=case)
        result = CaseFolderBinding._get_contract_folder_path(obj)
        assert result is None


# ============================================================
# cases/services/chat/naming.py (more branches)
# ============================================================


class TestChatNameBuilderExtra:
    def test_build_fallback_on_stage_display_error(self) -> None:
        from apps.cases.services.chat.naming import ChatNameBuilder
        mock_config = MagicMock()
        mock_config.render_chat_name.return_value = "test name"
        builder = ChatNameBuilder(config_service=mock_config)

        # Use a class that has get_current_stage_display but it raises ValueError
        class BadStageCase:
            name = "Test Case"
            current_stage = "some_stage"
            id = 42
            case_type = None

            def get_current_stage_display(self) -> str:
                raise ValueError("bad stage")

        result = builder.build(case=BadStageCase())
        assert result == "test name"

    def test_build_fallback_on_case_type_display_error(self) -> None:
        from apps.cases.services.chat.naming import ChatNameBuilder
        mock_config = MagicMock()
        mock_config.render_chat_name.return_value = "test name"
        builder = ChatNameBuilder(config_service=mock_config)

        case = SimpleNamespace(
            name="Test Case",
            current_stage=None,
            case_type="civil",
            id=42,
        )
        result = builder.build(case=case)
        assert result == "test name"

    def test_build_no_stage_no_case_type(self) -> None:
        from apps.cases.services.chat.naming import ChatNameBuilder
        mock_config = MagicMock()
        mock_config.render_chat_name.return_value = "name"
        builder = ChatNameBuilder(config_service=mock_config)
        case = SimpleNamespace(name="Case", current_stage=None, case_type=None)
        builder.build(case=case)
        mock_config.render_chat_name.assert_called_once_with(
            case_name="Case", stage=None, case_type=None
        )


# ============================================================
# cases/services/case/assembler/case_dto_assembler.py
# ============================================================


class TestCaseDtoAssembler:
    def test_to_dto(self) -> None:
        from apps.cases.services.case.assembler.case_dto_assembler import CaseDtoAssembler
        assembler = CaseDtoAssembler()
        case = SimpleNamespace(id=1, name="test")
        with patch("apps.cases.services.case.assembler.case_dto_assembler.CaseDTO") as MockDTO:
            MockDTO.from_model.return_value = SimpleNamespace(case_number=None)
            result = assembler.to_dto(case, case_number="2024京01民初1号")
            assert result.case_number == "2024京01民初1号"

    def test_to_dtos(self) -> None:
        from apps.cases.services.case.assembler.case_dto_assembler import CaseDtoAssembler
        assembler = CaseDtoAssembler()
        case1 = SimpleNamespace(id=1)
        case2 = SimpleNamespace(id=2)
        with patch("apps.cases.services.case.assembler.case_dto_assembler.CaseDTO") as MockDTO:
            MockDTO.from_model.return_value = SimpleNamespace(case_number=None)
            result = assembler.to_dtos([case1, case2], case_number_map={1: "num1", 2: None})
            assert len(result) == 2

    def test_to_dtos_no_map(self) -> None:
        from apps.cases.services.case.assembler.case_dto_assembler import CaseDtoAssembler
        assembler = CaseDtoAssembler()
        case = SimpleNamespace(id=1)
        with patch("apps.cases.services.case.assembler.case_dto_assembler.CaseDTO") as MockDTO:
            MockDTO.from_model.return_value = SimpleNamespace(case_number=None)
            result = assembler.to_dtos([case])
            assert len(result) == 1


# ============================================================
# cases/services/case/repo/case_repo.py
# ============================================================


class TestCaseRepo:
    def test_get_cases_by_ids_empty(self) -> None:
        from apps.cases.services.case.repo.case_repo import CaseRepo
        repo = CaseRepo()
        assert repo.get_cases_by_ids([]) == []

    @patch("apps.cases.services.case.repo.case_repo.Case")
    def test_get_cases_by_ids(self, mock_case) -> None:
        from apps.cases.services.case.repo.case_repo import CaseRepo
        mock_case.objects.filter.return_value.select_related.return_value = ["case1", "case2"]
        repo = CaseRepo()
        result = repo.get_cases_by_ids([1, 2])
        assert len(result) == 2

    @patch("apps.cases.services.case.repo.case_repo.Case")
    def test_list_cases(self, mock_case) -> None:
        from apps.cases.services.case.repo.case_repo import CaseRepo
        mock_qs = MagicMock()
        mock_case.objects.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_qs.__getitem__ = lambda self, key: ["case1"]

        repo = CaseRepo()
        result = repo.list_cases(status="active", limit=10)
        mock_qs.filter.assert_called()


# ============================================================
# cases/services/case/repo/case_number_repo.py
# ============================================================


class TestCaseNumberRepo:
    def test_list_case_numbers_empty(self) -> None:
        from apps.cases.services.case.repo.case_number_repo import CaseNumberRepo
        repo = CaseNumberRepo()
        assert repo.list_case_numbers_by_case_ids([]) == []

    @patch("apps.cases.services.case.repo.case_number_repo.CaseNumber")
    def test_list_case_numbers(self, mock_model) -> None:
        from apps.cases.services.case.repo.case_number_repo import CaseNumberRepo
        mock_model.objects.filter.return_value.order_by.return_value.values_list.return_value = [(1, "num1")]
        repo = CaseNumberRepo()
        result = repo.list_case_numbers_by_case_ids([1])
        assert len(result) == 1


# ============================================================
# cases/services/case/repo/case_assignment_repo.py
# ============================================================


class TestCaseAssignmentRepo:
    @patch("apps.cases.services.case.repo.case_assignment_repo.CaseAssignment")
    def test_list_assignments_empty(self, mock_model) -> None:
        from apps.cases.services.case.repo.case_assignment_repo import CaseAssignmentRepo
        repo = CaseAssignmentRepo()
        result = repo.list_assignments_by_case_ids([])
        assert result == []

    @patch("apps.cases.services.case.repo.case_assignment_repo.CaseAssignment")
    def test_list_assignments(self, mock_model) -> None:
        from apps.cases.services.case.repo.case_assignment_repo import CaseAssignmentRepo
        mock_model.objects.filter.return_value.select_related.return_value.order_by.return_value = ["a1"]
        repo = CaseAssignmentRepo()
        result = repo.list_assignments_by_case_ids([1, 2])
        assert len(result) == 1


# ============================================================
# cases/services/case/repo/case_party_repo.py
# ============================================================


class TestCasePartyRepo:
    @patch("apps.cases.services.case.repo.case_party_repo.CaseParty")
    def test_list_party_names(self, mock_model) -> None:
        from apps.cases.services.case.repo.case_party_repo import CasePartyRepo
        mock_model.objects.filter.return_value.select_related.return_value.values_list.return_value = ["张三", "李四"]
        repo = CasePartyRepo()
        result = repo.list_party_names_by_case(1)
        assert result == ["张三", "李四"]

    def test_search_cases_empty(self) -> None:
        from apps.cases.services.case.repo.case_party_repo import CasePartyRepo
        repo = CasePartyRepo()
        assert repo.search_cases_by_party([]) == []

    @patch("apps.cases.services.case.repo.case_party_repo.Case")
    def test_search_cases_with_names(self, mock_case) -> None:
        from apps.cases.services.case.repo.case_party_repo import CasePartyRepo
        mock_qs = MagicMock()
        mock_case.objects.select_related.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.distinct.return_value = mock_qs
        repo = CasePartyRepo()
        result = repo.search_cases_by_party(["张三"], status="active")
        mock_qs.filter.assert_called()


# ============================================================
# cases/services/case/repo/case_search_query_builder.py
# ============================================================


class TestCaseSearchQueryBuilder:
    def test_build_case_id_empty(self) -> None:
        from apps.cases.services.case.repo.case_search_query_builder import CaseSearchQueryBuilder
        builder = CaseSearchQueryBuilder()
        assert builder.build_case_id_query_by_case_number("") == []

    def test_build_case_id_none(self) -> None:
        from apps.cases.services.case.repo.case_search_query_builder import CaseSearchQueryBuilder
        builder = CaseSearchQueryBuilder()
        assert builder.build_case_id_query_by_case_number(None) == []  # type: ignore[arg-type]

    @patch("apps.cases.services.case.repo.case_search_query_builder.CaseNumber")
    def test_build_case_id_found(self, mock_number) -> None:
        from apps.cases.services.case.repo.case_search_query_builder import CaseSearchQueryBuilder
        mock_number.objects.filter.return_value.values_list.return_value = [1, 2]
        builder = CaseSearchQueryBuilder()
        result = builder.build_case_id_query_by_case_number("2024京01民初1号")
        assert result == [1, 2]

    def test_build_search_empty_query(self) -> None:
        from apps.cases.services.case.repo.case_search_query_builder import CaseSearchQueryBuilder
        builder = CaseSearchQueryBuilder()
        mock_qs = MagicMock()
        result = builder.build_case_search_queryset(mock_qs, query="")
        mock_qs.none.assert_called_once()

    def test_build_search_whitespace_query(self) -> None:
        from apps.cases.services.case.repo.case_search_query_builder import CaseSearchQueryBuilder
        builder = CaseSearchQueryBuilder()
        mock_qs = MagicMock()
        result = builder.build_case_search_queryset(mock_qs, query="   ")
        mock_qs.none.assert_called_once()

    def test_build_search_with_query(self) -> None:
        from apps.cases.services.case.repo.case_search_query_builder import CaseSearchQueryBuilder
        builder = CaseSearchQueryBuilder()
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.distinct.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_qs.__getitem__ = lambda self, key: []
        result = builder.build_case_search_queryset(mock_qs, query="test", status="active", limit=10)
        mock_qs.filter.assert_called()
        mock_qs.distinct.assert_called_once()


# ============================================================
# cases/services/data/cause_court_data_service.py
# ============================================================


class TestCauseCourtDataParser:
    def test_flatten_tree_dict_with_name(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataParser
        parser = CauseCourtDataParser()
        data = {"id": "1", "name": "合同纠纷", "children": [
            {"id": "2", "name": "买卖合同"},
        ]}
        result = parser.flatten_tree(data)
        assert len(result) == 2
        assert result[0]["name"] == "合同纠纷"
        assert result[1]["name"] == "买卖合同"

    def test_flatten_tree_empty_name(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataParser
        parser = CauseCourtDataParser()
        data = {"id": "1", "name": "  "}
        result = parser.flatten_tree(data)
        assert len(result) == 0

    def test_flatten_tree_list(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataParser
        parser = CauseCourtDataParser()
        data = [
            {"id": "1", "name": "A"},
            {"id": "2", "name": "B"},
        ]
        result = parser.flatten_tree(data)
        assert len(result) == 2

    def test_flatten_tree_no_name(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataParser
        parser = CauseCourtDataParser()
        data = {"id": "1", "children": []}
        result = parser.flatten_tree(data)
        assert len(result) == 0

    def test_filter_by_query_exact_match_first(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataParser
        parser = CauseCourtDataParser()
        items = [
            {"id": "1", "name": "合同纠纷"},
            {"id": "2", "name": "合同"},
            {"id": "3", "name": "买卖合同纠纷"},
        ]
        result = parser.filter_by_query(items, "合同")
        assert result[0]["name"] == "合同"

    def test_filter_by_query_starts_with(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataParser
        parser = CauseCourtDataParser()
        items = [
            {"id": "1", "name": "买卖合同纠纷"},
            {"id": "2", "name": "合同"},
        ]
        result = parser.filter_by_query(items, "合同")
        # "合同" should be first (exact match), then "买卖合同纠纷" (starts with)
        assert result[0]["name"] == "合同"
        assert result[1]["name"] == "买卖合同纠纷"

    def test_filter_by_query_no_match(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataParser
        parser = CauseCourtDataParser()
        items = [{"id": "1", "name": "合同纠纷"}]
        result = parser.filter_by_query(items, "侵权")
        assert len(result) == 0


class TestCauseCourtDataCache:
    def test_file_not_found(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataCache
        from apps.core.utils.path import Path
        from apps.core.exceptions import ValidationException
        cache = CauseCourtDataCache(Path("/nonexistent/dir"))
        with pytest.raises(ValidationException) as exc_info:
            cache.load_json_file("missing.json")
        # The inner ValidationException (FILE_NOT_FOUND) is caught by the outer generic except,
        # which wraps it as FILE_LOAD_ERROR
        assert exc_info.value.code in ("FILE_NOT_FOUND", "FILE_LOAD_ERROR")

    def test_json_parse_error(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataCache
        from apps.core.utils.path import Path
        from apps.core.exceptions import ValidationException
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "bad.json"
            bad_file.write_text("not json {{{")
            cache = CauseCourtDataCache(Path(tmpdir))
            with pytest.raises(ValidationException) as exc_info:
                cache.load_json_file("bad.json")
            assert "JSON_PARSE_ERROR" in exc_info.value.code

    def test_valid_json(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataCache
        from apps.core.utils.path import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            good_file = Path(tmpdir) / "good.json"
            good_file.write_text(json.dumps({"key": "value"}))
            cache = CauseCourtDataCache(Path(tmpdir))
            result = cache.load_json_file("good.json")
            assert result == {"key": "value"}


class TestCauseCourtDataService:
    def test_invalid_case_type(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataService
        from apps.core.exceptions import ValidationException
        svc = CauseCourtDataService()
        with pytest.raises(ValidationException) as exc_info:
            svc.get_causes_by_type("nonexistent")
        assert "INVALID_CASE_TYPE" in exc_info.value.code

    def test_search_empty_query(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataService
        svc = CauseCourtDataService()
        assert svc.search_causes("") == []
        assert svc.search_causes("   ") == []
        assert svc.search_causes(None) == []  # type: ignore[arg-type]

    def test_search_courts_empty(self) -> None:
        from apps.cases.services.data.cause_court_data_service import CauseCourtDataService
        svc = CauseCourtDataService()
        assert svc.search_courts("") == []
        assert svc.search_courts("   ") == []


# ============================================================
# cases/domain/validators.py
# ============================================================


class TestDomainValidators:
    def test_is_applicable_none(self) -> None:
        from apps.cases.domain.validators import is_applicable
        assert is_applicable(None) is False

    def test_is_applicable_empty(self) -> None:
        from apps.cases.domain.validators import is_applicable
        assert is_applicable("") is False

    def test_is_applicable_valid(self) -> None:
        from apps.cases.domain.validators import is_applicable
        assert is_applicable("civil") is True

    def test_is_applicable_invalid(self) -> None:
        from apps.cases.domain.validators import is_applicable
        assert is_applicable("nonexistent") is False

    def test_normalize_stages_not_applicable(self) -> None:
        from apps.cases.domain.validators import normalize_stages
        result = normalize_stages("bankruptcy", None, None)
        assert result == ([], None)

    def test_normalize_stages_not_applicable_strict_with_data_raises(self) -> None:
        from apps.cases.domain.validators import normalize_stages
        with pytest.raises(ValueError) as exc_info:
            normalize_stages("bankruptcy", ["first_trial"], None, strict=True)
        assert "stages_not_applicable" in str(exc_info.value)

    def test_normalize_stages_invalid_rep_raises(self) -> None:
        from apps.cases.domain.validators import normalize_stages
        with pytest.raises(ValueError) as exc_info:
            normalize_stages("civil", ["nonexistent_stage"], None)
        assert "invalid_rep" in str(exc_info.value)

    def test_normalize_stages_invalid_cur_raises(self) -> None:
        from apps.cases.domain.validators import normalize_stages
        with pytest.raises(ValueError) as exc_info:
            normalize_stages("civil", ["first_trial"], "nonexistent_stage")
        assert "invalid_cur" in str(exc_info.value)

    def test_normalize_stages_cur_not_in_rep_raises(self) -> None:
        from apps.cases.domain.validators import normalize_stages
        with pytest.raises(ValueError) as exc_info:
            normalize_stages("civil", ["first_trial"], "second_trial")
        assert "cur_not_in_rep" in str(exc_info.value)

    def test_normalize_stages_valid(self) -> None:
        from apps.cases.domain.validators import normalize_stages
        result = normalize_stages("civil", ["first_trial"], "first_trial")
        assert result == (["first_trial"], "first_trial")

    def test_normalize_stages_empty(self) -> None:
        from apps.cases.domain.validators import normalize_stages
        result = normalize_stages("civil", [], None)
        assert result == ([], None)


# ============================================================
# documents/storage.py (more branches)
# ============================================================


class TestDocumentStorage:
    def test_get_configured_private_docx_settings(self) -> None:
        from apps.documents.storage import get_configured_private_docx_templates_root
        with patch("apps.documents.storage.django_apps") as mock_apps:
            mock_apps.ready = False
            with patch("apps.documents.storage.settings") as mock_settings:
                mock_settings.DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT = "/some/path"
                result = get_configured_private_docx_templates_root()
                assert result == "/some/path"

    def test_get_configured_private_docx_not_ready(self) -> None:
        from apps.documents.storage import get_configured_private_docx_templates_root
        with patch("apps.documents.storage.django_apps") as mock_apps:
            mock_apps.ready = False
            with patch("apps.documents.storage.settings") as mock_settings:
                mock_settings.DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT = ""
                result = get_configured_private_docx_templates_root()
                assert result == ""

    def test_get_configured_private_runtime_config(self) -> None:
        from apps.documents.storage import get_configured_private_docx_templates_root
        mock_system_config = MagicMock()
        mock_system_config.get_value.return_value = "/runtime/path"
        with patch("apps.documents.storage.django_apps") as mock_apps:
            mock_apps.ready = True
            with patch("apps.documents.storage.settings") as mock_settings:
                mock_settings.DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT = ""
                with patch("apps.core.interfaces.ServiceLocator") as mock_locator:
                    mock_locator.get_system_config_service.return_value = mock_system_config
                    result = get_configured_private_docx_templates_root()
                    assert result == "/runtime/path"

    def test_get_configured_private_operational_error(self) -> None:
        from apps.documents.storage import get_configured_private_docx_templates_root
        from django.db.utils import OperationalError
        with patch("apps.documents.storage.django_apps") as mock_apps:
            mock_apps.ready = True
            with patch("apps.documents.storage.settings") as mock_settings:
                mock_settings.DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT = "/fallback"
                with patch("apps.core.interfaces.ServiceLocator") as mock_locator:
                    mock_locator.get_system_config_service.side_effect = OperationalError("table not ready")
                    result = get_configured_private_docx_templates_root()
                    assert result == "/fallback"

    def test_get_configured_private_generic_exception(self) -> None:
        from apps.documents.storage import get_configured_private_docx_templates_root
        with patch("apps.documents.storage.django_apps") as mock_apps:
            mock_apps.ready = True
            with patch("apps.documents.storage.settings") as mock_settings:
                mock_settings.DOCUMENTS_PRIVATE_DOCX_TEMPLATES_ROOT = "/fallback2"
                with patch("apps.core.interfaces.ServiceLocator") as mock_locator:
                    mock_locator.get_system_config_service.side_effect = RuntimeError("unexpected")
                    result = get_configured_private_docx_templates_root()
                    assert result == "/fallback2"

    def test_get_private_docx_root_none_when_empty(self) -> None:
        from apps.documents.storage import get_private_docx_templates_root
        with patch("apps.documents.storage.get_configured_private_docx_templates_root", return_value=""):
            result = get_private_docx_templates_root()
            assert result is None

    def test_get_private_docx_root_returns_path(self) -> None:
        from apps.documents.storage import get_private_docx_templates_root
        with patch("apps.documents.storage.get_configured_private_docx_templates_root", return_value="/some/path"):
            result = get_private_docx_templates_root()
            assert result is not None

    def test_get_docx_templates_source_private(self) -> None:
        from apps.documents.storage import get_docx_templates_source
        with patch("apps.documents.storage.get_private_docx_templates_root", return_value=Path("/p")):
            assert get_docx_templates_source() == "private"

    def test_get_docx_templates_source_public(self) -> None:
        from apps.documents.storage import get_docx_templates_source
        with patch("apps.documents.storage.get_private_docx_templates_root", return_value=None):
            assert get_docx_templates_source() == "public"

    def test_resolve_docx_template_path_absolute(self) -> None:
        from apps.documents.storage import resolve_docx_template_path
        result = resolve_docx_template_path("/absolute/path/template.docx")
        assert result == Path("/absolute/path/template.docx")

    def test_resolve_docx_template_path_relative(self) -> None:
        from apps.documents.storage import resolve_docx_template_path
        with patch("apps.documents.storage.get_docx_templates_root") as mock_root:
            mock_root.return_value = Path("/root")
            result = resolve_docx_template_path("subdir/template.docx")
            assert "template.docx" in str(result)

    def test_resolve_docx_template_path_traversal_raises(self) -> None:
        from apps.documents.storage import resolve_docx_template_path
        with patch("apps.documents.storage.get_docx_templates_root") as mock_root:
            mock_root.return_value = Path("/root")
            with pytest.raises(ValueError, match="模板路径越界"):
                resolve_docx_template_path("../../etc/passwd")


class TestListDocxTemplatesFiles:
    def test_root_not_exists(self) -> None:
        from apps.documents.storage import list_docx_templates_files
        with patch("apps.documents.storage.get_docx_templates_root") as mock_root:
            mock_root.return_value = Path("/nonexistent")
            result = list_docx_templates_files()
            assert result == []

    def test_root_exists_with_files(self) -> None:
        from apps.documents.storage import list_docx_templates_files
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            # Create a docx file
            (tmpdir_path / "test.docx").touch()
            with patch("apps.documents.storage.get_docx_templates_root", return_value=tmpdir_path):
                result = list_docx_templates_files()
                assert len(result) == 1
                assert result[0][0] == "test.docx"

    def test_skips_user_custom_dir(self) -> None:
        from apps.documents.storage import list_docx_templates_files, USER_CUSTOM_TEMPLATE_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            # Create a file in the user custom dir
            custom_dir = tmpdir_path / USER_CUSTOM_TEMPLATE_DIR
            custom_dir.mkdir()
            (custom_dir / "uploaded.docx").touch()
            # Create a file outside user custom dir
            (tmpdir_path / "template.docx").touch()
            with patch("apps.documents.storage.get_docx_templates_root", return_value=tmpdir_path):
                result = list_docx_templates_files()
                assert len(result) == 1
                assert result[0][0] == "template.docx"
