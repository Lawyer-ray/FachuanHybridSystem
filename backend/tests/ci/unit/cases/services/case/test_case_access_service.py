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


@pytest.mark.django_db
class TestCaseAccessServiceCreateGrantFirmScope:
    """安全审计（2026-10-19）：create/batch 授权前校验发起人对案件的访问权（律所口径）。"""

    def test_create_grant_denies_cross_firm_admin(self) -> None:
        """A 所管理员不能给仅有 B 所指派的案件授权"""
        from apps.cases.models import Case, CaseAssignment
        from apps.cases.services.case.case_access_service import CaseAccessService
        from apps.organization.models import LawFirm, Lawyer
        from apps.testing.factories import CaseFactory, LawyerFactory

        firm_a = LawFirm.objects.create(name="授权甲所")  # privacy-allow 虚构律所
        firm_b = LawFirm.objects.create(name="授权乙所")  # privacy-allow 虚构律所
        admin_a = LawyerFactory(is_admin=True, law_firm=firm_a)
        lawyer_b = LawyerFactory(law_firm=firm_b)
        grantee = Lawyer.objects.create_user(username="grant_grantee", real_name="被授权人")
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=lawyer_b)

        svc = CaseAccessService()
        with pytest.raises(ForbiddenError):
            svc.create_grant(case_id=case.id, grantee_id=grantee.id, user=admin_a)
        assert not Case.objects.filter(pk=case.pk, access_grants__grantee_id=grantee.id).exists()

    def test_batch_grant_access_denies_cross_firm_admin(self) -> None:
        """A 所管理员不能批量给仅有 B 所指派的案件授权"""
        from apps.cases.models import CaseAssignment
        from apps.cases.services.case.case_access_service import CaseAccessService
        from apps.organization.models import LawFirm
        from apps.testing.factories import CaseFactory, LawyerFactory

        firm_a = LawFirm.objects.create(name="批量授权甲所")  # privacy-allow 虚构律所
        firm_b = LawFirm.objects.create(name="批量授权乙所")  # privacy-allow 虚构律所
        admin_a = LawyerFactory(is_admin=True, law_firm=firm_a)
        lawyer_b = LawyerFactory(law_firm=firm_b)
        grantee = LawyerFactory()
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=lawyer_b)

        svc = CaseAccessService()
        with pytest.raises(ForbiddenError):
            svc.batch_grant_access(case_id=case.id, grantee_ids=[grantee.id], user=admin_a)

    def test_create_grant_allows_same_firm_admin(self) -> None:
        """本所指派覆盖的案件：本所管理员可正常授权（正控）"""
        from apps.cases.models import CaseAssignment
        from apps.cases.services.case.case_access_service import CaseAccessService
        from apps.organization.models import LawFirm
        from apps.testing.factories import CaseFactory, LawyerFactory

        firm = LawFirm.objects.create(name="授权同所")
        admin = LawyerFactory(is_admin=True, law_firm=firm)
        member = LawyerFactory(law_firm=firm)
        grantee = LawyerFactory()
        case = CaseFactory()
        CaseAssignment.objects.create(case=case, lawyer=member)

        grant = CaseAccessService().create_grant(case_id=case.id, grantee_id=grantee.id, user=admin)
        assert grant.case_id == case.id
        assert grant.grantee_id == grantee.id
