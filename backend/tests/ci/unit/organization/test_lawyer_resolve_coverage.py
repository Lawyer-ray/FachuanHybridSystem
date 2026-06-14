"""补充覆盖测试: organization/services/lawyer_resolve_service.py (37 missing)

覆盖: resolve 所有分支 (phone/username/创建), _unique_username,
缓存命中路径。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.organization.services.lawyer_resolve_service import LawyerResolveService


class TestResolve:
    @pytest.mark.django_db
    def test_no_phone_no_username_returns_none(self) -> None:
        svc = LawyerResolveService()
        result = svc.resolve({})
        assert result is None

    @pytest.mark.django_db
    def test_returns_none_when_only_username_not_found(self) -> None:
        svc = LawyerResolveService()
        # username provided but not found, and no phone -> returns None
        with patch("apps.organization.services.lawyer_resolve_service.Lawyer") as MockLawyer:
            MockLawyer.objects.filter.return_value.first.return_value = None
            result = svc.resolve({"username": "nonexistent"})
            assert result is None

    @pytest.mark.django_db
    def test_phone_cache_hit(self) -> None:
        svc = LawyerResolveService()
        mock_lawyer = MagicMock()
        mock_lawyer.pk = 1
        svc._cache["13800000000"] = mock_lawyer
        result = svc.resolve({"phone": "13800000000"})
        assert result is mock_lawyer

    @pytest.mark.django_db
    def test_username_cache_hit(self) -> None:
        svc = LawyerResolveService()
        mock_lawyer = MagicMock()
        mock_lawyer.pk = 2
        svc._cache["__username__testuser"] = mock_lawyer
        result = svc.resolve({"username": "testuser"})
        assert result is mock_lawyer

    @pytest.mark.django_db
    def test_phone_lookup_found(self) -> None:
        svc = LawyerResolveService()
        mock_lawyer = MagicMock()
        mock_lawyer.pk = 3

        with patch("apps.organization.services.lawyer_resolve_service.Lawyer") as MockLawyer:
            MockLawyer.objects.filter.return_value.first.return_value = mock_lawyer
            result = svc.resolve({"phone": "13800000001"})
            assert result is mock_lawyer
            assert "13800000001" in svc._cache

    @pytest.mark.django_db
    def test_username_lookup_found(self) -> None:
        svc = LawyerResolveService()
        mock_lawyer = MagicMock()
        mock_lawyer.pk = 4

        with patch("apps.organization.services.lawyer_resolve_service.Lawyer") as MockLawyer:
            # phone lookup returns None, username lookup returns lawyer
            MockLawyer.objects.filter.return_value.first.return_value = None
            MockLawyer.objects.filter.return_value.first.side_effect = None
            # First call: phone lookup (returns None), Second call: username lookup (returns lawyer)
            MockLawyer.objects.filter.side_effect = [
                MagicMock(first=MagicMock(return_value=None)),  # phone lookup
                MagicMock(first=MagicMock(return_value=mock_lawyer)),  # username lookup
            ]
            result = svc.resolve({"phone": "13800000002", "username": "found_user"})
            assert result is mock_lawyer

    @pytest.mark.django_db
    def test_creates_new_lawyer(self) -> None:
        svc = LawyerResolveService()
        mock_lawyer = MagicMock()
        mock_lawyer.pk = 5

        with patch("apps.organization.services.lawyer_resolve_service.Lawyer") as MockLawyer:
            MockLawyer.objects.filter.return_value.first.return_value = None
            MockLawyer.objects.filter.return_value.exists.return_value = False
            MockLawyer.objects.create_user.return_value = mock_lawyer
            result = svc.resolve({"phone": "13800000003", "real_name": "张三"})
            assert result is mock_lawyer
            MockLawyer.objects.create_user.assert_called_once()

    @pytest.mark.django_db
    def test_creates_new_lawyer_with_name_fallback(self) -> None:
        svc = LawyerResolveService()
        mock_lawyer = MagicMock()
        mock_lawyer.pk = 6

        with patch("apps.organization.services.lawyer_resolve_service.Lawyer") as MockLawyer:
            MockLawyer.objects.filter.return_value.first.return_value = None
            MockLawyer.objects.filter.return_value.exists.return_value = False
            MockLawyer.objects.create_user.return_value = mock_lawyer
            # No real_name, no name -> fallback to phone
            result = svc.resolve({"phone": "13800000004"})
            assert result is mock_lawyer


class TestUniqueUsername:
    @pytest.mark.django_db
    def test_unique_when_no_collision(self) -> None:
        svc = LawyerResolveService()
        with patch("apps.organization.services.lawyer_resolve_service.Lawyer") as MockLawyer:
            MockLawyer.objects.filter.return_value.exists.return_value = False
            result = svc._unique_username("base")
            assert result == "base"

    @pytest.mark.django_db
    def test_unique_with_collision(self) -> None:
        svc = LawyerResolveService()
        with patch("apps.organization.services.lawyer_resolve_service.Lawyer") as MockLawyer:
            # First call: "base" exists, second call: "base_2" exists, third: "base_3" doesn't
            MockLawyer.objects.filter.return_value.exists.side_effect = [True, True, False]
            result = svc._unique_username("base")
            assert result == "base_3"
