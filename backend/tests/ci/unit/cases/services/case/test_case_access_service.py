"""Unit tests for cases.services.case.case_access_service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ConflictError, ForbiddenError, NotFoundError


class TestCaseAccessServiceInit:
    """Test constructor."""

    def test_init_with_defaults(self) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        assert svc._case_service is None

    def test_init_with_injected(self) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        case_svc = MagicMock()
        svc = CaseAccessService(case_service=case_svc)
        assert svc._case_service is case_svc


class TestCaseAccessServiceListGrants:
    """list_grants tests."""

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    def test_perm_open_access_returns_all(self, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        mock_qs = MagicMock()
        mock_grant_cls.objects.all.return_value.order_by.return_value.select_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        result = svc.list_grants(perm_open_access=True)
        mock_qs.filter.assert_not_called()

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    def test_filters_by_case_id(self, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = False
        user.id = 1
        mock_qs = MagicMock()
        mock_grant_cls.objects.all.return_value.order_by.return_value.select_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        svc.list_grants(case_id=5, user=user)
        mock_qs.filter.assert_any_call(case_id=5)

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    def test_filters_by_grantee_id(self, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = False
        user.id = 1
        mock_qs = MagicMock()
        mock_grant_cls.objects.all.return_value.order_by.return_value.select_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        svc.list_grants(grantee_id=10, user=user)
        mock_qs.filter.assert_any_call(grantee_id=10)

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    def test_regular_user_forbidden_for_others_grants(self, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        user = MagicMock()
        user.is_authenticated = False
        user.is_superuser = False
        user.id = 1
        mock_qs = MagicMock()
        mock_grant_cls.objects.all.return_value.order_by.return_value.select_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        with pytest.raises(ForbiddenError):
            svc.list_grants(grantee_id=999, user=user)

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    def test_super_user_sees_all(self, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = True
        user.id = 1
        mock_qs = MagicMock()
        mock_grant_cls.objects.all.return_value.order_by.return_value.select_related.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        result = svc.list_grants(grantee_id=999, user=user)
        assert result is mock_qs


class TestCaseAccessServiceGetGrant:
    """get_grant tests."""

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    def test_not_found(self, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        mock_grant_cls.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_grant_cls.objects.select_related.return_value.get.side_effect = mock_grant_cls.DoesNotExist()
        with pytest.raises(NotFoundError):
            svc.get_grant(1, perm_open_access=True)

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    def test_perm_open_access(self, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        grant = MagicMock()
        mock_grant_cls.objects.select_related.return_value.get.return_value = grant
        result = svc.get_grant(1, perm_open_access=True)
        assert result is grant

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    def test_authenticated_user_can_view_own_grant(self, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        grant = MagicMock()
        grant.grantee_id = 10
        mock_grant_cls.objects.select_related.return_value.get.return_value = grant
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = False
        user.id = 10
        result = svc.get_grant(1, user=user)
        assert result is grant

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    def test_regular_user_forbidden_for_others_grant(self, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        grant = MagicMock()
        grant.grantee_id = 999
        mock_grant_cls.objects.select_related.return_value.get.return_value = grant
        user = MagicMock()
        user.is_authenticated = False
        user.is_superuser = False
        user.id = 10
        with pytest.raises(ForbiddenError):
            svc.get_grant(1, user=user)


class TestCaseAccessServiceGetGrantsForUser:
    """get_grants_for_user tests."""

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    def test_regular_user_can_see_own(self, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = False
        user.id = 10
        mock_qs = MagicMock()
        mock_grant_cls.objects.filter.return_value.select_related.return_value = mock_qs
        result = svc.get_grants_for_user(user_id=10, user=user)
        assert result is mock_qs

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    def test_regular_user_forbidden_for_others(self, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        user = MagicMock()
        user.is_authenticated = False
        user.is_superuser = False
        user.id = 10
        with pytest.raises(ForbiddenError):
            svc.get_grants_for_user(user_id=999, user=user)


class TestCaseAccessServiceGetAccessibleCaseIds:
    """get_accessible_case_ids tests."""

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    def test_returns_set(self, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = False
        user.id = 10
        mock_grant_cls.objects.filter.return_value.values_list.return_value = [1, 2, 3]
        result = svc.get_accessible_case_ids(user_id=10, user=user)
        assert result == {1, 2, 3}

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    def test_super_user_can_see_others(self, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = True
        user.id = 10
        mock_grant_cls.objects.filter.return_value.values_list.return_value = [5, 6]
        result = svc.get_accessible_case_ids(user_id=999, user=user)
        assert result == {5, 6}


class TestCaseAccessServiceRevokeAccess:
    """revoke_access tests."""

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    @patch("apps.cases.services.case.case_access_service.invalidate_user_access_context")
    def test_not_found(self, mock_invalidate, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        mock_grant_cls.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_grant_cls.objects.get.side_effect = mock_grant_cls.DoesNotExist()
        with pytest.raises(NotFoundError):
            svc.revoke_access(case_id=1, grantee_id=10, user=MagicMock(is_admin=True))

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    @patch("apps.cases.services.case.case_access_service.invalidate_user_access_context")
    def test_successful_revoke(self, mock_invalidate, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        grant = MagicMock()
        grant.grantee_id = 10
        mock_grant_cls.objects.get.return_value = grant
        user = MagicMock()
        user.is_admin = True
        result = svc.revoke_access(case_id=1, grantee_id=10, user=user)
        assert result is True
        grant.delete.assert_called_once()
        mock_invalidate.assert_called_once_with(10)


class TestCaseAccessServiceRevokeAccessById:
    """revoke_access_by_id tests."""

    @patch("apps.cases.services.case.case_access_service.CaseAccessGrant")
    @patch("apps.cases.services.case.case_access_service.invalidate_user_access_context")
    def test_returns_true(self, mock_invalidate, mock_grant_cls) -> None:
        from apps.cases.services.case.case_access_service import CaseAccessService

        svc = CaseAccessService()
        grant = MagicMock()
        grant.grantee_id = 10
        mock_grant_cls.objects.select_related.return_value.get.return_value = grant
        user = MagicMock()
        user.is_admin = True
        result = svc.revoke_access_by_id(grant_id=1, user=user)
        assert result is True
