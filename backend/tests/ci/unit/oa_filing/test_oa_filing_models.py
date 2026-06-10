"""oa_filing app Model 单元测试

覆盖 FilingSession, CaseImportSession, ClientImportSession, OAConfig 的
__str__、choices。
"""

import pytest

from apps.oa_filing.models.case_import_session import CaseImportPhase, CaseImportSession, CaseImportStatus
from apps.oa_filing.models.client_import_session import ClientImportPhase, ClientImportSession, ClientImportStatus
from apps.oa_filing.models.filing_session import FilingSession, SessionStatus
from apps.oa_filing.models.oa_config import OAConfig
from apps.testing.factories import ContractFactory, LawyerFactory


# ============================================================
# FilingSession
# ============================================================


@pytest.mark.django_db
class TestFilingSession:
    def test_str(self):
        contract = ContractFactory()
        lawyer = LawyerFactory()
        session = FilingSession.objects.create(
            contract=contract,
            user=lawyer,
            status=SessionStatus.PENDING,
        )
        result = str(session)
        assert "FilingSession" in result
        assert "pending" in result

    def test_status_choices(self):
        assert SessionStatus.PENDING.value == "pending"
        assert SessionStatus.IN_PROGRESS.value == "in_progress"
        assert SessionStatus.COMPLETED.value == "completed"
        assert SessionStatus.FAILED.value == "failed"
        assert SessionStatus.CANCELLED.value == "cancelled"

    def test_default_status(self):
        contract = ContractFactory()
        lawyer = LawyerFactory()
        session = FilingSession.objects.create(
            contract=contract,
            user=lawyer,
        )
        assert session.status == SessionStatus.PENDING

    def test_error_message_default(self):
        contract = ContractFactory()
        lawyer = LawyerFactory()
        session = FilingSession.objects.create(
            contract=contract,
            user=lawyer,
        )
        assert session.error_message == ""


# ============================================================
# CaseImportSession
# ============================================================


@pytest.mark.django_db
class TestCaseImportSession:
    def test_str(self):
        lawyer = LawyerFactory()
        session = CaseImportSession.objects.create(
            lawyer=lawyer,
            status=CaseImportStatus.PENDING,
        )
        result = str(session)
        assert "CaseImportSession" in result
        assert "pending" in result

    def test_status_choices(self):
        assert CaseImportStatus.PENDING.value == "pending"
        assert CaseImportStatus.IN_PROGRESS.value == "in_progress"
        assert CaseImportStatus.COMPLETED.value == "completed"
        assert CaseImportStatus.FAILED.value == "failed"

    def test_phase_choices(self):
        assert CaseImportPhase.PARSING.value == "parsing"
        assert CaseImportPhase.PREVIEW.value == "preview"
        assert CaseImportPhase.DISCOVERING.value == "discovering"
        assert CaseImportPhase.IMPORTING.value == "importing"

    def test_default_counts(self):
        lawyer = LawyerFactory()
        session = CaseImportSession.objects.create(lawyer=lawyer)
        assert session.total_count == 0
        assert session.matched_count == 0
        assert session.unmatched_count == 0
        assert session.success_count == 0
        assert session.skip_count == 0
        assert session.error_count == 0

    def test_default_phase(self):
        lawyer = LawyerFactory()
        session = CaseImportSession.objects.create(lawyer=lawyer)
        assert session.phase == CaseImportPhase.PENDING


# ============================================================
# ClientImportSession
# ============================================================


@pytest.mark.django_db
class TestClientImportSession:
    def test_str(self):
        lawyer = LawyerFactory()
        session = ClientImportSession.objects.create(
            lawyer=lawyer,
            status=ClientImportStatus.PENDING,
        )
        result = str(session)
        assert "ClientImportSession" in result
        assert "pending" in result

    def test_status_choices(self):
        assert ClientImportStatus.PENDING.value == "pending"
        assert ClientImportStatus.COMPLETED.value == "completed"
        assert ClientImportStatus.FAILED.value == "failed"

    def test_phase_choices(self):
        assert ClientImportPhase.DISCOVERING.value == "discovering"
        assert ClientImportPhase.IMPORTING.value == "importing"

    def test_default_counts(self):
        lawyer = LawyerFactory()
        session = ClientImportSession.objects.create(lawyer=lawyer)
        assert session.discovered_count == 0
        assert session.total_count == 0
        assert session.success_count == 0
        assert session.skip_count == 0


# ============================================================
# OAConfig
# ============================================================


@pytest.mark.django_db
class TestOAConfig:
    def test_str(self):
        config = OAConfig.objects.create(site_name="一张网OA")
        assert str(config) == "一张网OA"

    def test_default_is_enabled(self):
        config = OAConfig.objects.create(site_name="test_site")
        assert config.is_enabled is True

    def test_field_mapping_default(self):
        config = OAConfig.objects.create(site_name="test_site2")
        assert config.field_mapping == {}

    def test_unique_site_name(self):
        OAConfig.objects.create(site_name="unique_site")
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            OAConfig.objects.create(site_name="unique_site")
