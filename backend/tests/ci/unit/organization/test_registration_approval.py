"""注册 → 审批 闭环的语义测试（2026-11-25 恢复注册功能）。

覆盖三条产品语义：
1. 首位用户（系统尚无**已激活**账号）注册即成律所管理员，并触发系统初始化；
2. 后续用户注册为待审批状态，必须管理员审批后才能登录；
3. 历史上的 ``is_active=False`` 孤儿行不再永久占死首位名额。

回归背景：``is_active`` 曾绑定在默认 False 的 ``ALLOW_FIRST_USER_SUPERUSER`` 上，
导致任何注册产出的账号都永远登不上，而响应还谎称「请等待管理员审批」——
系统里当时根本没有审批入口。本文件守住修好后的不变量。
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from django.contrib.auth import authenticate

from apps.core.exceptions import NotFoundError, PermissionDenied
from apps.organization.models import LawFirm, Lawyer
from apps.organization.services.auth.auth_service import AuthService
from apps.organization.services.lawyer.approval import LawyerApprovalService

PASSWORD = "Zz!8kQm2pLx7"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _no_active_account() -> Iterator[None]:
    """每个用例开始前，把系统置于「尚无可登录账号」——首位用户语义的前置条件。

    ``AuthService.is_first_user()``（``apps/organization/services/auth/auth_service.py:66``）
    的判据是「``organization_lawyer`` 里没有任何 ``is_active=True`` 的行」，这是**库级
    全局状态**，不是本文件造出来的数据。全量跑时只要排在前面的一条用例把
    ``is_active=True`` 的行**提交**进了测试库（``django_db`` 用例自己会 rollback，但走
    另一条连接/线程的写入不会），本文件这 3 条「首位用户」用例就会整体判成
    「不是首位用户」：``granted_admin is False`` / ``authenticate(...) is None`` /
    ``FirstUserSetupService.execute`` 一次都没被调用；单独跑本文件时又全绿——
    **绿灯取决于跑在哪个用例之后，等于没有护栏**。

    做法是把前置条件显式化，断言因此与执行顺序无关。用 ``update(is_active=False)``
    而不是 ``delete()``：``organization_lawyer`` 被 ``cases.CaseLog`` /
    ``contracts.FinanceLog`` / ``ContractAssignment`` 等以 ``PROTECT`` 引用，泄漏行
    一旦带上这些关联，``delete()`` 会抛 ``ProtectedError``，把「断言红」升级成
    「fixture 炸」；而这里要的只是「没有可登录账号」，降级即可，不必删行。

    只降级 ``is_active=True``：``is_active=False`` 的历史孤儿行正是
    ``test_inactive_ghost_does_not_block_first_user`` 要守的场景，一并清掉就等于把
    待测前提删掉了。
    """
    Lawyer.objects.filter(is_active=True).update(is_active=False)
    yield


@pytest.fixture
def no_setup() -> Iterator[None]:
    """跳过系统初始化（律所/团队/SystemConfig/文书模板），只验证注册语义。"""
    with patch("apps.organization.services.auth.auth_service.FirstUserSetupService"):
        yield


def _make_admin(law_firm: LawFirm) -> Lawyer:
    return Lawyer.objects.create_user(
        username="boss", password=PASSWORD, is_admin=True, is_active=True, law_firm=law_firm
    )


# ── 首位用户：注册即律所管理员 ────────────────────────────────────────────


@pytest.mark.django_db
def test_first_user_becomes_law_firm_admin(no_setup: None) -> None:
    result = AuthService().register("first", PASSWORD, real_name="第一人")

    assert result.is_first_user is True
    assert result.granted_admin is True
    user = Lawyer.objects.get(username="first")
    assert user.is_active is True
    assert user.is_admin is True
    assert user.is_staff is True
    # 平台超级管理员仍受 ALLOW_FIRST_USER_SUPERUSER 管控，默认不授予（安全审计 C-02）
    assert user.is_superuser is False


@pytest.mark.django_db
def test_first_user_can_login(no_setup: None) -> None:
    AuthService().register("first", PASSWORD)

    assert authenticate(username="first", password=PASSWORD) is not None


@pytest.mark.django_db
def test_first_user_triggers_system_setup() -> None:
    with patch("apps.organization.services.auth.auth_service.FirstUserSetupService") as setup:
        AuthService().register("first", PASSWORD)
    setup.return_value.execute.assert_called_once()


# ── 后续用户：待审批 ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_second_user_requires_approval(no_setup: None) -> None:
    AuthService().register("first", PASSWORD)

    result = AuthService().register("second", PASSWORD)

    assert result.is_first_user is False
    assert result.granted_admin is False
    second = Lawyer.objects.get(username="second")
    assert second.is_active is False
    assert second.is_admin is False


@pytest.mark.django_db
def test_second_user_cannot_login_before_approval(no_setup: None) -> None:
    AuthService().register("first", PASSWORD)
    AuthService().register("second", PASSWORD)

    assert authenticate(username="second", password=PASSWORD) is None


@pytest.mark.django_db
def test_inactive_ghost_does_not_block_first_user(no_setup: None) -> None:
    """历史孤儿行（注册后无人审批）不能再永久占死首位名额。"""
    Lawyer.objects.create_user(username="ghost", password=PASSWORD, is_active=False)

    result = AuthService().register("first", PASSWORD)

    assert result.granted_admin is True
    assert Lawyer.objects.get(username="first").is_active is True


# ── 审批闭环 ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_approve_activates_and_assigns_law_firm(no_setup: None) -> None:
    firm = LawFirm.objects.create(name="测试律所")
    admin = _make_admin(firm)
    pending = Lawyer.objects.create_user(username="waiting", password=PASSWORD, is_active=False)

    assert [p.username for p in LawyerApprovalService().list_pending(admin)] == ["waiting"]

    approved = LawyerApprovalService().approve(pending.pk, admin)

    assert approved.is_active is True
    assert approved.law_firm_id == firm.pk
    assert LawyerApprovalService().list_pending(admin) == []
    assert authenticate(username="waiting", password=PASSWORD) is not None


@pytest.mark.django_db
def test_reject_deletes_pending(no_setup: None) -> None:
    firm = LawFirm.objects.create(name="测试律所")
    admin = _make_admin(firm)
    pending = Lawyer.objects.create_user(username="waiting", password=PASSWORD, is_active=False)

    LawyerApprovalService().reject(pending.pk, admin)

    assert not Lawyer.objects.filter(username="waiting").exists()


@pytest.mark.django_db
def test_non_admin_cannot_list_or_approve(no_setup: None) -> None:
    ordinary = Lawyer.objects.create_user(username="plain", password=PASSWORD, is_active=True)
    pending = Lawyer.objects.create_user(username="waiting", password=PASSWORD, is_active=False)

    with pytest.raises(PermissionDenied):
        LawyerApprovalService().list_pending(ordinary)
    with pytest.raises(PermissionDenied):
        LawyerApprovalService().approve(pending.pk, ordinary)


@pytest.mark.django_db
def test_approve_already_active_is_not_found(no_setup: None) -> None:
    firm = LawFirm.objects.create(name="测试律所")
    admin = _make_admin(firm)
    active = Lawyer.objects.create_user(username="already", password=PASSWORD, is_active=True)

    with pytest.raises(NotFoundError):
        LawyerApprovalService().approve(active.pk, admin)
