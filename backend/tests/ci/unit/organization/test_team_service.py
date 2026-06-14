"""Tests for organization/services/team_service.py (missing: 26 lines).

Covers: get_team, update_team, delete_team, _validate_team_type,
permission-denied branches, law_firm not found branches.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from apps.organization.dtos import TeamUpsertDTO
from apps.organization.services.team_service import TeamService


@pytest.fixture
def svc() -> TeamService:
    return TeamService()


# ── get_team ───────────────────────────────────────────────────────────────


class TestGetTeam:
    @patch("apps.organization.services.team_service.Team")
    def test_team_not_found(self, mock_team_cls: MagicMock, svc: TeamService) -> None:
        mock_team_cls.objects.select_related.return_value.filter.return_value.first.return_value = None
        with pytest.raises(NotFoundError, match="团队不存在"):
            svc.get_team(999)

    @patch("apps.organization.services.team_service.Team")
    def test_team_found_no_user(self, mock_team_cls: MagicMock, svc: TeamService) -> None:
        team = MagicMock()
        mock_team_cls.objects.select_related.return_value.filter.return_value.first.return_value = team
        result = svc.get_team(1, user=None)
        assert result is team

    @patch("apps.organization.services.team_service.Team")
    def test_team_found_with_user_no_permission(self, mock_team_cls: MagicMock, svc: TeamService) -> None:
        team = MagicMock()
        team.law_firm_id = 10
        mock_team_cls.objects.select_related.return_value.filter.return_value.first.return_value = team
        user = MagicMock()
        user.law_firm_id = 99  # different
        user.is_authenticated = True
        user.is_superuser = False
        with pytest.raises(PermissionDenied, match="无权限"):
            svc.get_team(1, user=user)

    @patch("apps.organization.services.team_service.Team")
    def test_team_found_with_user_has_permission(self, mock_team_cls: MagicMock, svc: TeamService) -> None:
        team = MagicMock()
        team.law_firm_id = 10
        mock_team_cls.objects.select_related.return_value.filter.return_value.first.return_value = team
        user = MagicMock()
        user.law_firm_id = 10
        user.is_authenticated = True
        result = svc.get_team(1, user=user)
        assert result is team


# ── update_team ────────────────────────────────────────────────────────────


class TestUpdateTeam:
    @pytest.mark.django_db
    @patch("apps.organization.services.team_service.LawFirm")
    @patch("apps.organization.services.team_service.Team")
    def test_update_team_permission_denied(
        self, mock_team_cls: MagicMock, mock_lawfirm_cls: MagicMock, svc: TeamService
    ) -> None:
        team = MagicMock()
        team.id = 1
        team.law_firm_id = 10
        mock_team_cls.objects.select_related.return_value.filter.return_value.first.return_value = team
        user = MagicMock()
        user.id = 999
        user.law_firm_id = 99
        user.is_authenticated = True
        user.is_superuser = False
        user.is_admin = False

        data = TeamUpsertDTO(name="Test", team_type="lawyer", law_firm_id=10)
        with pytest.raises(PermissionDenied, match="无权限"):
            svc.update_team(1, data, user=user)

    @pytest.mark.django_db
    @patch("apps.organization.services.team_service.LawFirm")
    @patch("apps.organization.services.team_service.Team")
    def test_update_team_lawfirm_not_found(
        self, mock_team_cls: MagicMock, mock_lawfirm_cls: MagicMock, svc: TeamService
    ) -> None:
        team = MagicMock()
        team.id = 1
        team.law_firm_id = 10
        mock_team_cls.objects.select_related.return_value.filter.return_value.first.return_value = team
        mock_lawfirm_cls.objects.filter.return_value.first.return_value = None
        user = MagicMock()
        user.id = 1
        user.law_firm_id = 10
        user.is_authenticated = True
        user.is_superuser = True

        data = TeamUpsertDTO(name="Test", team_type="lawyer", law_firm_id=999)
        with pytest.raises(NotFoundError, match="律所不存在"):
            svc.update_team(1, data, user=user)

    @pytest.mark.django_db
    @patch("apps.organization.services.team_service.LawFirm")
    @patch("apps.organization.services.team_service.Team")
    def test_update_team_success(
        self, mock_team_cls: MagicMock, mock_lawfirm_cls: MagicMock, svc: TeamService
    ) -> None:
        team = MagicMock()
        team.id = 1
        team.law_firm_id = 10
        mock_team_cls.objects.select_related.return_value.filter.return_value.first.return_value = team
        mock_lawfirm_cls.objects.filter.return_value.first.return_value = MagicMock()
        user = MagicMock()
        user.id = 1
        user.law_firm_id = 10
        user.is_authenticated = True
        user.is_superuser = True

        data = TeamUpsertDTO(name="Updated", team_type="biz", law_firm_id=10)
        svc.update_team(1, data, user=user)
        team.save.assert_called_once()

    @pytest.mark.django_db
    @patch("apps.organization.services.team_service.LawFirm")
    @patch("apps.organization.services.team_service.Team")
    def test_update_team_invalid_type(
        self, mock_team_cls: MagicMock, mock_lawfirm_cls: MagicMock, svc: TeamService
    ) -> None:
        team = MagicMock()
        team.id = 1
        team.law_firm_id = 10
        mock_team_cls.objects.select_related.return_value.filter.return_value.first.return_value = team
        user = MagicMock()
        user.id = 1
        user.law_firm_id = 10
        user.is_authenticated = True
        user.is_superuser = True

        data = TeamUpsertDTO(name="Test", team_type="INVALID", law_firm_id=10)
        with pytest.raises(ValidationException, match="非法团队类型"):
            svc.update_team(1, data, user=user)


# ── delete_team ────────────────────────────────────────────────────────────


class TestDeleteTeam:
    @pytest.mark.django_db
    @patch("apps.organization.services.team_service.Team")
    def test_delete_team_permission_denied(self, mock_team_cls: MagicMock, svc: TeamService) -> None:
        team = MagicMock()
        team.id = 1
        team.law_firm_id = 10
        mock_team_cls.objects.select_related.return_value.filter.return_value.first.return_value = team
        user = MagicMock()
        user.id = 999
        user.law_firm_id = 99
        user.is_authenticated = True
        user.is_superuser = False
        user.is_admin = False

        with pytest.raises(PermissionDenied, match="无权限"):
            svc.delete_team(1, user=user)

    @pytest.mark.django_db
    @patch("apps.organization.services.team_service.Team")
    def test_delete_team_success(self, mock_team_cls: MagicMock, svc: TeamService) -> None:
        team = MagicMock()
        team.id = 1
        team.law_firm_id = 10
        mock_team_cls.objects.select_related.return_value.filter.return_value.first.return_value = team
        user = MagicMock()
        user.id = 1
        user.law_firm_id = 10
        user.is_authenticated = True
        user.is_superuser = True

        svc.delete_team(1, user=user)
        team.delete.assert_called_once()


# ── _validate_team_type ───────────────────────────────────────────────────


class TestValidateTeamType:
    def test_invalid_type_raises(self, svc: TeamService) -> None:
        with pytest.raises(ValidationException, match="非法团队类型"):
            svc._validate_team_type("NONEXISTENT")
