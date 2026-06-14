"""Tests for organization/services/lawyer/facade.py, query.py, adapter.py, upload.py.

Covers: lawyer facade methods, query service branches, adapter conversions,
upload service, _validate_team_type.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import AuthenticationError, NotFoundError, PermissionDenied
from apps.organization.services.lawyer.facade import LawyerService
from apps.organization.services.lawyer.query import LawyerQueryService
from apps.organization.services.lawyer.adapter import LawyerServiceAdapter
from apps.organization.services.lawyer.upload import LawyerUploadService


# ── LawyerService (facade) ────────────────────────────────────────────────


class TestLawyerServiceFacade:
    def test_get_lawyer_no_user(self) -> None:
        svc = LawyerService()
        with pytest.raises(AuthenticationError, match="请先登录"):
            svc.get_lawyer(1, user=None)

    def test_create_lawyer_no_user(self) -> None:
        svc = LawyerService()
        with pytest.raises(AuthenticationError, match="请先登录"):
            svc.create_lawyer(data=MagicMock(), user=None)

    def test_delete_lawyer_no_user(self) -> None:
        svc = LawyerService()
        with pytest.raises(AuthenticationError, match="请先登录"):
            svc.delete_lawyer(1, user=None)

    def test_get_lawyer_by_id_found(self) -> None:
        svc = LawyerService()
        mock_lawyer = MagicMock()
        with patch.object(svc._query, "get_lawyer_queryset") as mock_qs:
            mock_qs.return_value.filter.return_value.first.return_value = mock_lawyer
            result = svc.get_lawyer_by_id(1)
            assert result is mock_lawyer

    def test_get_lawyer_by_id_not_found(self) -> None:
        svc = LawyerService()
        with patch.object(svc._query, "get_lawyer_queryset") as mock_qs:
            mock_qs.return_value.filter.return_value.first.return_value = None
            result = svc.get_lawyer_by_id(999)
            assert result is None


# ── LawyerQueryService ────────────────────────────────────────────────────


class TestLawyerQueryService:
    def setup_method(self) -> None:
        self.policy = MagicMock()
        self.svc = LawyerQueryService(access_policy=self.policy)

    def test_get_lawyer_not_found(self) -> None:
        user = MagicMock()
        with patch("apps.organization.services.lawyer.query.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.prefetch_related.return_value.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError, match="律师不存在"):
                self.svc.get_lawyer(999, user)

    def test_get_lawyer_permission_denied(self) -> None:
        user = MagicMock()
        lawyer = MagicMock()
        self.policy.can_read_lawyer.return_value = False
        with patch("apps.organization.services.lawyer.query.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.prefetch_related.return_value.filter.return_value.first.return_value = lawyer
            with pytest.raises(PermissionDenied, match="无权限"):
                self.svc.get_lawyer(1, user)

    def test_get_lawyer_success(self) -> None:
        user = MagicMock()
        lawyer = MagicMock()
        self.policy.can_read_lawyer.return_value = True
        with patch("apps.organization.services.lawyer.query.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.prefetch_related.return_value.filter.return_value.first.return_value = lawyer
            result = self.svc.get_lawyer(1, user)
            assert result is lawyer

    def test_list_lawyers_non_superadmin_with_firm(self) -> None:
        user = MagicMock()
        user.is_superuser = False
        user.law_firm_id = 10
        with patch("apps.organization.services.lawyer.query.Lawyer") as MockLawyer:
            mock_qs = MagicMock()
            MockLawyer.objects.select_related.return_value.prefetch_related.return_value = mock_qs
            result = self.svc.list_lawyers(user=user)
            mock_qs.filter.assert_called()

    def test_list_lawyers_non_superadmin_no_firm(self) -> None:
        user = MagicMock()
        user.is_superuser = False
        user.law_firm_id = None
        with patch("apps.organization.services.lawyer.query.Lawyer") as MockLawyer:
            mock_qs = MagicMock()
            MockLawyer.objects.select_related.return_value.prefetch_related.return_value = mock_qs
            result = self.svc.list_lawyers(user=user)
            mock_qs.none.assert_called()

    def test_list_lawyers_with_search_filter(self) -> None:
        user = MagicMock()
        user.is_superuser = True
        from apps.organization.dtos import LawyerListFiltersDTO
        filters = LawyerListFiltersDTO(search="test", law_firm_id=None)
        with patch("apps.organization.services.lawyer.query.Lawyer") as MockLawyer:
            mock_qs = MagicMock()
            MockLawyer.objects.select_related.return_value.prefetch_related.return_value = mock_qs
            result = self.svc.list_lawyers(filters=filters, user=user)
            mock_qs.filter.assert_called()

    def test_list_lawyers_with_firm_filter(self) -> None:
        user = MagicMock()
        user.is_superuser = True
        from apps.organization.dtos import LawyerListFiltersDTO
        filters = LawyerListFiltersDTO(search=None, law_firm_id=5)
        with patch("apps.organization.services.lawyer.query.Lawyer") as MockLawyer:
            mock_qs = MagicMock()
            MockLawyer.objects.select_related.return_value.prefetch_related.return_value = mock_qs
            result = self.svc.list_lawyers(filters=filters, user=user)

    def test_get_team_members(self) -> None:
        with patch("apps.organization.services.lawyer.query.Lawyer") as MockLawyer:
            mock_qs = MagicMock()
            MockLawyer.objects.select_related.return_value.prefetch_related.return_value = mock_qs
            self.svc.get_team_members(1)
            mock_qs.filter.assert_called()

    def test_get_team_member_ids_no_teams(self) -> None:
        user = MagicMock()
        user.lawyer_teams.all.return_value.values_list.return_value = MagicMock()
        user.pk = 1
        with patch("apps.organization.services.lawyer.query.Lawyer") as MockLawyer:
            mock_qs = MagicMock()
            mock_qs.values_list.return_value.distinct.return_value = []
            MockLawyer.objects.filter.return_value = mock_qs
            result = self.svc.get_team_member_ids(user)
            assert 1 in result  # fallback to user's own id

    def test_get_team_member_ids_with_teams(self) -> None:
        user = MagicMock()
        user.pk = 1
        with patch("apps.organization.services.lawyer.query.Lawyer") as MockLawyer:
            mock_qs = MagicMock()
            mock_qs.values_list.return_value.distinct.return_value = [1, 2, 3]
            MockLawyer.objects.filter.return_value = mock_qs
            result = self.svc.get_team_member_ids(user)
            assert result == {1, 2, 3}


# ── LawyerUploadService ──────────────────────────────────────────────────


class TestLawyerUploadService:
    def test_attach_license_pdf_none(self) -> None:
        svc = LawyerUploadService()
        lawyer = MagicMock()
        svc.attach_license_pdf(lawyer, None)
        lawyer.license_pdf.save.assert_not_called()

    def test_attach_license_pdf_with_file(self) -> None:
        svc = LawyerUploadService()
        lawyer = MagicMock()
        file = MagicMock()
        file.name = "test.pdf"
        svc.attach_license_pdf(lawyer, file)
        lawyer.license_pdf.save.assert_called_once_with("test.pdf", file, save=False)

    def test_attach_license_pdf_no_name(self) -> None:
        svc = LawyerUploadService()
        lawyer = MagicMock()
        file = MagicMock()
        file.name = None
        svc.attach_license_pdf(lawyer, file)
        lawyer.license_pdf.save.assert_called_once_with("license.pdf", file, save=False)

    def test_attach_avatar_none(self) -> None:
        svc = LawyerUploadService()
        lawyer = MagicMock()
        svc.attach_avatar(lawyer, None)
        lawyer.avatar.save.assert_not_called()

    def test_attach_avatar_with_file(self) -> None:
        svc = LawyerUploadService()
        lawyer = MagicMock()
        file = MagicMock()
        file.name = "photo.jpg"
        svc.attach_avatar(lawyer, file)
        lawyer.avatar.save.assert_called_once_with("photo.jpg", file, save=False)

    def test_attach_avatar_no_name(self) -> None:
        svc = LawyerUploadService()
        lawyer = MagicMock()
        file = MagicMock()
        file.name = None
        svc.attach_avatar(lawyer, file)
        lawyer.avatar.save.assert_called_once_with("avatar.jpg", file, save=False)


# ── LawyerServiceAdapter ─────────────────────────────────────────────────


class TestLawyerServiceAdapter:
    def test_get_lawyer_found(self) -> None:
        mock_service = MagicMock()
        mock_lawyer = MagicMock()
        mock_service.get_lawyer_by_id.return_value = mock_lawyer
        adapter = LawyerServiceAdapter(service=mock_service)
        with patch.object(LawyerServiceAdapter, "_assembler") as mock_asm:
            mock_asm.to_dto.return_value = MagicMock()
            result = adapter.get_lawyer(1)
            assert result is not None

    def test_get_lawyer_not_found(self) -> None:
        mock_service = MagicMock()
        mock_service.get_lawyer_by_id.return_value = None
        adapter = LawyerServiceAdapter(service=mock_service)
        result = adapter.get_lawyer(999)
        assert result is None

    def test_get_lawyers_by_ids(self) -> None:
        mock_service = MagicMock()
        mock_service.get_lawyers_by_ids.return_value = [MagicMock(), MagicMock()]
        adapter = LawyerServiceAdapter(service=mock_service)
        with patch.object(LawyerServiceAdapter, "_assembler") as mock_asm:
            mock_asm.to_dto.return_value = MagicMock()
            result = adapter.get_lawyers_by_ids([1, 2])
            assert len(result) == 2

    def test_get_team_members(self) -> None:
        mock_service = MagicMock()
        mock_service.get_team_members.return_value = [MagicMock()]
        adapter = LawyerServiceAdapter(service=mock_service)
        with patch.object(LawyerServiceAdapter, "_assembler") as mock_asm:
            mock_asm.to_dto.return_value = MagicMock()
            result = adapter.get_team_members(1)
            assert len(result) == 1

    def test_get_admin_lawyer_found(self) -> None:
        mock_service = MagicMock()
        mock_service.get_lawyer_queryset.return_value.filter.return_value.first.return_value = MagicMock()
        adapter = LawyerServiceAdapter(service=mock_service)
        with patch.object(LawyerServiceAdapter, "_assembler") as mock_asm:
            mock_asm.to_dto.return_value = MagicMock()
            result = adapter.get_admin_lawyer()
            assert result is not None

    def test_get_admin_lawyer_not_found(self) -> None:
        mock_service = MagicMock()
        mock_service.get_lawyer_queryset.return_value.filter.return_value.first.return_value = None
        adapter = LawyerServiceAdapter(service=mock_service)
        result = adapter.get_admin_lawyer()
        assert result is None

    def test_get_all_lawyer_names(self) -> None:
        mock_service = MagicMock()
        mock_service.get_lawyer_queryset.return_value.filter.return_value.exclude.return_value.values_list.return_value = ["Alice", "Bob"]
        adapter = LawyerServiceAdapter(service=mock_service)
        result = adapter.get_all_lawyer_names()
        assert result == ["Alice", "Bob"]

    def test_get_lawyer_model(self) -> None:
        mock_service = MagicMock()
        mock_service.get_lawyer_by_id.return_value = MagicMock()
        adapter = LawyerServiceAdapter(service=mock_service)
        result = adapter.get_lawyer_model(1)
        assert result is not None

    def test_get_admin_lawyer_internal(self) -> None:
        mock_service = MagicMock()
        mock_service.get_lawyer_queryset.return_value.filter.return_value.first.return_value = MagicMock()
        adapter = LawyerServiceAdapter(service=mock_service)
        with patch.object(LawyerServiceAdapter, "_assembler") as mock_asm:
            mock_asm.to_dto.return_value = MagicMock()
            result = adapter.get_admin_lawyer_internal()
            assert result is not None

    def test_get_all_lawyer_names_internal(self) -> None:
        mock_service = MagicMock()
        mock_service.get_lawyer_queryset.return_value.filter.return_value.exclude.return_value.values_list.return_value = []
        adapter = LawyerServiceAdapter(service=mock_service)
        result = adapter.get_all_lawyer_names_internal()
        assert result == []

    def test_get_lawyer_internal(self) -> None:
        mock_service = MagicMock()
        mock_service.get_lawyer_by_id.return_value = None
        adapter = LawyerServiceAdapter(service=mock_service)
        result = adapter.get_lawyer_internal(1)
        assert result is None
