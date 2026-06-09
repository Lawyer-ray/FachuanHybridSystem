"""Comprehensive tests for chat_records and enterprise_data services."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.chat_records.models import ChatRecordProject
from apps.chat_records.services.core.project_service import ProjectService
from apps.core.exceptions import NotFoundError, ValidationException
from apps.testing.factories import LawyerFactory


# ── ChatRecordProject model tests ──


@pytest.mark.django_db
class TestChatRecordProjectModel:
    def test_project_str(self, db):
        project = ChatRecordProject.objects.create(name="TestProject")
        assert "TestProject" in str(project)

    def test_project_create(self, db):
        project = ChatRecordProject.objects.create(name="My Project", description="Description")
        assert project.pk is not None
        assert project.name == "My Project"

    def test_project_with_creator(self, db, law_firm):
        lawyer = LawyerFactory(law_firm=law_firm)
        project = ChatRecordProject.objects.create(name="Created Project", created_by=lawyer)
        assert project.created_by_id == lawyer.pk


# ── ProjectService tests ──


@pytest.mark.django_db
class TestProjectService:
    def test_create_project(self, db):
        svc = ProjectService()
        project = svc.create_project(name="New Project", description="Desc")
        assert project.pk is not None
        assert project.name == "New Project"

    def test_create_project_empty_name(self, db):
        svc = ProjectService()
        with pytest.raises(ValidationException):
            svc.create_project(name="")

    def test_create_project_whitespace_name(self, db):
        svc = ProjectService()
        with pytest.raises(ValidationException):
            svc.create_project(name="   ")

    def test_list_projects_admin(self, db, law_firm):
        svc = ProjectService()
        ChatRecordProject.objects.create(name="P1")
        ChatRecordProject.objects.create(name="P2")
        admin = LawyerFactory(is_admin=True, law_firm=law_firm)
        qs = svc.list_projects(user=admin)
        assert qs.count() >= 2

    def test_list_projects_non_admin(self, db, law_firm):
        svc = ProjectService()
        lawyer = LawyerFactory(law_firm=law_firm)
        ChatRecordProject.objects.create(name="P1", created_by=lawyer)
        ChatRecordProject.objects.create(name="P2")
        qs = svc.list_projects(user=lawyer)
        assert qs.count() == 1

    def test_get_project(self, db, law_firm):
        svc = ProjectService()
        admin = LawyerFactory(is_admin=True, law_firm=law_firm)
        project = ChatRecordProject.objects.create(name="Get Project")
        result = svc.get_project(user=admin, project_id=project.pk)
        assert result.pk == project.pk

    def test_get_project_not_found(self, db, law_firm):
        svc = ProjectService()
        admin = LawyerFactory(is_admin=True, law_firm=law_firm)
        with pytest.raises(NotFoundError):
            svc.get_project(user=admin, project_id=99999)


# ── EnterpriseDataMetricsService tests ──


class TestEnterpriseDataMetricsService:
    def test_init_defaults(self):
        from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService

        svc = EnterpriseDataMetricsService()
        assert svc._window_seconds >= 60

    def test_init_custom(self):
        from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService

        svc = EnterpriseDataMetricsService(
            window_seconds=120,
            alert_min_samples=5,
            alert_success_rate_threshold=0.95,
            alert_fallback_rate_threshold=0.1,
            alert_avg_latency_ms_threshold=500,
        )
        assert svc._window_seconds == 120
        assert svc._alert_min_samples == 5

    def test_record_and_snapshot(self):
        from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService

        svc = EnterpriseDataMetricsService(window_seconds=60)
        result = svc.record(
            provider="test",
            capability="search",
            success=True,
            duration_ms=100,
            fallback_used=False,
        )
        assert result["total"] >= 1
        assert result["success"] >= 1

        snapshot = svc.snapshot(provider="test", capability="search")
        assert snapshot is not None
        assert snapshot["total"] >= 1

    def test_snapshot_empty(self):
        from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService

        svc = EnterpriseDataMetricsService()
        result = svc.snapshot(provider="nonexistent", capability="none")
        assert result is None

    def test_record_failure(self):
        from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService

        svc = EnterpriseDataMetricsService(window_seconds=60)
        result = svc.record(
            provider="test",
            capability="lookup",
            success=False,
            duration_ms=200,
            fallback_used=True,
        )
        assert result["failure"] >= 1
        assert result["fallback"] >= 1


# ── EnterpriseProviderRegistry tests ──


@pytest.mark.django_db
class TestEnterpriseProviderRegistry:
    def test_list_providers(self):
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        registry = EnterpriseProviderRegistry()
        providers = registry.list_providers()
        assert isinstance(providers, list)

    def test_get_default_provider_name(self):
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        registry = EnterpriseProviderRegistry()
        name = registry.get_default_provider_name()
        assert isinstance(name, str) or name is None


# ── EnterpriseDataService tests ──


@pytest.mark.django_db
class TestEnterpriseDataService:
    def test_list_providers(self):
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        result = svc.list_providers()
        assert "items" in result
        assert isinstance(result["items"], list)

    def test_list_providers_with_tools(self):
        from apps.enterprise_data.services.enterprise_data_service import EnterpriseDataService

        svc = EnterpriseDataService()
        result = svc.list_providers(include_tools=True)
        assert "items" in result


# ── EnterpriseData types tests ──


class TestEnterpriseDataTypes:
    def test_provider_response(self):
        from apps.enterprise_data.services.types import ProviderResponse

        resp = ProviderResponse(data={"name": "Test"}, raw={}, tool="search")
        assert resp.data == {"name": "Test"}
        assert resp.tool == "search"

    def test_provider_response_meta(self):
        from apps.enterprise_data.services.types import ProviderResponse

        resp = ProviderResponse(data=None, raw=None, tool="lookup", meta={"key": "value"})
        assert resp.meta == {"key": "value"}
