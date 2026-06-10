"""Batch8 coverage tests for apps.oa_filing."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ── OA Exceptions ─────────────────────────────────────────────────────────


class TestOAExceptions:
    """Test OA exception classes."""

    def test_oa_filing_error_default(self) -> None:
        from apps.oa_filing.services.exceptions import OAFilingError

        err = OAFilingError()
        assert err.message == ""
        assert str(err) == ""

    def test_oa_filing_error_message(self) -> None:
        from apps.oa_filing.services.exceptions import OAFilingError

        err = OAFilingError("test error")
        assert err.message == "test error"
        assert str(err) == "test error"

    def test_script_execution_error_default(self) -> None:
        from apps.oa_filing.services.exceptions import ScriptExecutionError

        err = ScriptExecutionError()
        assert "脚本执行失败" in err.message

    def test_script_execution_error_custom(self) -> None:
        from apps.oa_filing.services.exceptions import ScriptExecutionError

        err = ScriptExecutionError("custom error")
        assert err.message == "custom error"


# ── ImportSessionService ──────────────────────────────────────────────────


class TestImportSessionService:
    """Test import session service functions."""

    def test_get_case_session_or_none_not_found(self, db: None) -> None:
        from apps.oa_filing.services.import_session_service import get_case_session_or_none

        result = get_case_session_or_none(99999)
        assert result is None

    def test_get_client_session_or_none_not_found(self, db: None) -> None:
        from apps.oa_filing.services.import_session_service import get_client_session_or_none

        result = get_client_session_or_none(99999)
        assert result is None

    def test_get_jtn_credential_not_found(self, db: None) -> None:
        from apps.oa_filing.services.import_session_service import get_jtn_credential

        result = get_jtn_credential(99999)
        assert result is None

    def test_get_lawyer_not_found(self, db: None) -> None:
        from apps.oa_filing.services.import_session_service import get_lawyer

        with pytest.raises(Exception):
            get_lawyer(99999)

    def test_client_exists_by_name_false(self, db: None) -> None:
        from apps.oa_filing.services.import_session_service import client_exists_by_name

        result = client_exists_by_name("NonexistentClient")
        assert result is False

    def test_client_exists_by_id_number_false(self, db: None) -> None:
        from apps.oa_filing.services.import_session_service import client_exists_by_id_number

        result = client_exists_by_id_number("000000000000000000")
        assert result is False

    def test_client_exists_by_name_true(self, db: None) -> None:
        from apps.oa_filing.services.import_session_service import client_exists_by_name
        from apps.client.models import Client

        Client.objects.create(name="ExistTest", client_type="natural")
        result = client_exists_by_name("ExistTest")
        assert result is True


# ── ClientImportService ───────────────────────────────────────────────────


class TestClientImportService:
    """Test ClientImportService."""

    def test_to_int_valid(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        assert ClientImportService._to_int("42") == 42

    def test_to_int_invalid(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        assert ClientImportService._to_int("abc") == 0

    def test_to_int_none(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        assert ClientImportService._to_int(None) == 0

    def test_import_result_dataclass(self) -> None:
        from apps.oa_filing.services.client_import_service import ImportResult

        result = ImportResult(status="created", message="ok")
        assert result.status == "created"
        assert result.message == "ok"


# ── OA HTML Parser ────────────────────────────────────────────────────────


class TestOAHtmlParser:
    """Test OA HTML parser functions."""

    def test_normalize_text_none(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import normalize_text

        assert normalize_text(None) == ""

    def test_normalize_text_spaces(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import normalize_text

        assert normalize_text("  hello  world  ") == "hello world"

    def test_normalize_text_fullwidth_space(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import normalize_text

        result = normalize_text("hello\xa0world")
        assert "\xa0" not in result

    def test_normalize_label(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import normalize_label

        result = normalize_label("案件名称：")
        assert "：" not in result
        assert ":" not in result

    def test_iter_label_value_pairs(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import iter_label_value_pairs

        cells = ["案件名称", "测试案件", "案号", "2024-001"]
        pairs = iter_label_value_pairs(cells)
        assert len(pairs) == 2
        assert pairs[0][0] == "案件名称"
        assert pairs[0][1] == "测试案件"


# ── OA Filing Models ──────────────────────────────────────────────────────


class TestOAFilingModels:
    """Test OA filing models."""

    def test_oa_config_str(self, db: None) -> None:
        from apps.oa_filing.models import OAConfig

        config = OAConfig.objects.create(site_name="test_site")
        result = str(config)
        assert "test_site" in result or str(config.id) in result

    def test_case_import_session_str(self, db: None) -> None:
        from apps.oa_filing.models import CaseImportSession
        from apps.organization.models import LawFirm, Lawyer

        firm = LawFirm.objects.create(name="OAFirm")
        lawyer = Lawyer.objects.create_user(username="oauser", password="p", law_firm=firm)
        session = CaseImportSession.objects.create(lawyer=lawyer, status="pending")
        result = str(session)
        assert str(session.id) in result

    def test_client_import_session_str(self, db: None) -> None:
        from apps.oa_filing.models import ClientImportSession
        from apps.organization.models import LawFirm, Lawyer

        firm = LawFirm.objects.create(name="OAFirm2")
        lawyer = Lawyer.objects.create_user(username="oauser2", password="p", law_firm=firm)
        session = ClientImportSession.objects.create(lawyer=lawyer, status="pending")
        result = str(session)
        assert str(session.id) in result


# ── OA Filing Schemas ─────────────────────────────────────────────────────


class TestOAFilingSchemas:
    """Test OA filing schemas."""

    def test_case_import_schemas_import(self) -> None:
        from apps.oa_filing.schemas.case_import_schemas import (
            CaseImportSessionOut,
            CasePreviewItem,
        )
        assert CaseImportSessionOut is not None
        assert CasePreviewItem is not None

    def test_client_import_schemas_import(self) -> None:
        from apps.oa_filing.schemas.client_import_schemas import ClientImportSessionOut
        assert ClientImportSessionOut is not None

    def test_filing_schemas_import(self) -> None:
        from apps.oa_filing.schemas.filing_schemas import SessionOut, OAConfigOut
        assert SessionOut is not None
        assert OAConfigOut is not None


# ── OA Filing Constants ───────────────────────────────────────────────────


class TestOAFilingConstants:
    """Test OA filing constants."""

    def test_filing_constants_import(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.filing import constants

        assert hasattr(constants, "_LOGIN_URL")
        assert hasattr(constants, "_FILING_URL")

    def test_filing_models_import(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.filing import filing_models

        assert hasattr(filing_models, "FilingFormState")
        assert hasattr(filing_models, "ClientInfo")


# ── OA Filing Tasks ───────────────────────────────────────────────────────


class TestOAFilingTasks:
    """Test OA filing tasks module."""

    def test_tasks_import(self) -> None:
        from apps.oa_filing import tasks
        assert tasks is not None


# ── OA Models ─────────────────────────────────────────────────────────────


class TestOAImportModels:
    """Test OA import models."""

    def test_oa_case_data_import(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.models import OACaseData

        assert OACaseData is not None

    def test_oa_case_info_data_import(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.models import OACaseInfoData

        assert OACaseInfoData is not None

    def test_sso_handler_import(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import import sso_handler

        assert hasattr(sso_handler, "JtnSsoHandlerMixin")
