"""Tests for social_auth services.

登录策略是「只放行已绑定的社交身份，绝不自动建号」，因此这里的重点是
未绑定必须被拒绝、以及两条唯一约束（一个身份一位律师 / 一位律师一个平台一个账号）。
服务层内部实现是同步函数，直接用真实数据库测，比 mock async ORM 更贴近行为。
"""

from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from django.db import IntegrityError

from apps.organization.models import Lawyer
from apps.social_auth.models import SocialAccount
from apps.social_auth.providers.base import SocialProfile
from apps.social_auth.services import (
    SocialAccountConflictError,
    SocialAccountNotBoundError,
    SocialAccountNotFoundError,
    SocialAccountProviderOccupiedError,
    unbind_social_account,
)
from apps.social_auth.services.social_auth_service import _bind_social_account_to_user_sync, _resolve_bound_user_sync


def _profile(provider: str = "feishu", uid: str = "ou_abc", **overrides: object) -> SocialProfile:
    data: dict[str, object] = {
        "provider": provider,
        "provider_user_id": uid,
        "email": None,
        "display_name": "张三",
        "avatar_url": "https://example.com/avatar.jpg",
        "raw_data": {"open_id": uid},
    }
    data.update(overrides)
    return SocialProfile(**data)  # type: ignore[arg-type]


@pytest.fixture
def lawyer(db: None) -> Lawyer:
    created: Lawyer = Lawyer.objects.create_user(username="lawyer_a", password="x", real_name="张三")
    return created


class TestResolveBoundUser:
    @pytest.mark.django_db
    def test_unbound_identity_is_rejected(self) -> None:
        with pytest.raises(SocialAccountNotBoundError):
            _resolve_bound_user_sync(_profile())

    @pytest.mark.django_db
    def test_bound_identity_returns_owner(self, lawyer: Lawyer) -> None:
        SocialAccount.objects.create(user=lawyer, provider="feishu", provider_uid="ou_abc")
        assert _resolve_bound_user_sync(_profile()) == lawyer

    @pytest.mark.django_db
    def test_resolve_refreshes_platform_profile(self, lawyer: Lawyer) -> None:
        account = SocialAccount.objects.create(user=lawyer, provider="feishu", provider_uid="ou_abc")
        _resolve_bound_user_sync(_profile(display_name="新昵称", avatar_url="https://example.com/new.jpg"))
        account.refresh_from_db()
        assert account.display_name == "新昵称"
        assert account.avatar_url == "https://example.com/new.jpg"

    @pytest.mark.django_db
    def test_same_uid_on_other_provider_is_not_matched(self, lawyer: Lawyer) -> None:
        """uid 只在平台内唯一，跨平台不能串号。"""
        SocialAccount.objects.create(user=lawyer, provider="wechat", provider_uid="ou_abc")
        with pytest.raises(SocialAccountNotBoundError):
            _resolve_bound_user_sync(_profile(provider="feishu"))


class TestBindSocialAccount:
    @pytest.mark.django_db
    def test_bind_creates_link(self, lawyer: Lawyer) -> None:
        account = _bind_social_account_to_user_sync(_profile(), lawyer)
        assert account.user_id == lawyer.id
        assert account.provider_uid == "ou_abc"

    @pytest.mark.django_db
    def test_rebinding_same_identity_is_idempotent(self, lawyer: Lawyer) -> None:
        first = _bind_social_account_to_user_sync(_profile(), lawyer)
        second = _bind_social_account_to_user_sync(_profile(display_name="新昵称"), lawyer)
        assert first.pk == second.pk
        assert second.display_name == "新昵称"
        assert SocialAccount.objects.filter(user=lawyer, provider="feishu").count() == 1

    @pytest.mark.django_db
    def test_identity_owned_by_other_lawyer_conflicts(self, lawyer: Lawyer) -> None:
        other = Lawyer.objects.create_user(username="lawyer_b", password="x")
        SocialAccount.objects.create(user=other, provider="feishu", provider_uid="ou_abc")
        with pytest.raises(SocialAccountConflictError):
            _bind_social_account_to_user_sync(_profile(), lawyer)

    @pytest.mark.django_db
    def test_second_account_on_same_provider_is_rejected(self, lawyer: Lawyer) -> None:
        """一位律师每个平台只能绑一个账号，换绑需先解绑。"""
        SocialAccount.objects.create(user=lawyer, provider="feishu", provider_uid="ou_first")
        with pytest.raises(SocialAccountProviderOccupiedError):
            _bind_social_account_to_user_sync(_profile(uid="ou_second"), lawyer)

    @pytest.mark.django_db
    def test_one_lawyer_can_bind_multiple_providers(self, lawyer: Lawyer) -> None:
        _bind_social_account_to_user_sync(_profile(), lawyer)
        _bind_social_account_to_user_sync(_profile(provider="wechat", uid="wx_1"), lawyer)
        assert SocialAccount.objects.filter(user=lawyer).count() == 2

    @pytest.mark.django_db
    def test_different_lawyers_bind_different_identities(self, lawyer: Lawyer) -> None:
        other = Lawyer.objects.create_user(username="lawyer_b", password="x")
        _bind_social_account_to_user_sync(_profile(), lawyer)
        _bind_social_account_to_user_sync(_profile(provider="wechat", uid="wx_1"), other)
        assert SocialAccount.objects.filter(user=lawyer).count() == 1
        assert SocialAccount.objects.filter(user=other).count() == 1


class TestSocialAccountConstraints:
    """约束是最后一道防线：并发/绕过服务层时也不能写出歧义数据。"""

    @pytest.mark.django_db
    def test_identity_cannot_belong_to_two_lawyers(self, lawyer: Lawyer) -> None:
        other = Lawyer.objects.create_user(username="lawyer_b", password="x")
        SocialAccount.objects.create(user=lawyer, provider="feishu", provider_uid="ou_abc")
        with pytest.raises(IntegrityError):
            SocialAccount.objects.create(user=other, provider="feishu", provider_uid="ou_abc")

    @pytest.mark.django_db
    def test_lawyer_cannot_hold_two_accounts_on_same_provider(self, lawyer: Lawyer) -> None:
        SocialAccount.objects.create(user=lawyer, provider="feishu", provider_uid="ou_abc")
        with pytest.raises(IntegrityError):
            SocialAccount.objects.create(user=lawyer, provider="feishu", provider_uid="ou_xyz")


class TestUnbindSocialAccount:
    """用 ``async_to_sync`` 驱动 async 服务，而非 ``transaction=True`` + ``mark.asyncio``。

    async ORM 会在独立线程的连接上执行，看不到 ``django_db`` 事务里未提交的数据；
    改成 TransactionTestCase 又要承担 teardown flush 与 post-migrate
    create_permissions 竞争的风险（见 test_e2e_system_config_branch 的说明）。
    """

    @pytest.mark.django_db
    def test_unbind_removes_only_that_provider(self, lawyer: Lawyer) -> None:
        SocialAccount.objects.create(user=lawyer, provider="feishu", provider_uid="ou_abc")
        SocialAccount.objects.create(user=lawyer, provider="wechat", provider_uid="wx_1")

        async_to_sync(unbind_social_account)(lawyer, "feishu")

        remaining = list(SocialAccount.objects.filter(user=lawyer).values_list("provider", flat=True))
        assert remaining == ["wechat"]

    @pytest.mark.django_db
    def test_unbind_missing_binding_raises(self, lawyer: Lawyer) -> None:
        with pytest.raises(SocialAccountNotFoundError):
            async_to_sync(unbind_social_account)(lawyer, "feishu")
