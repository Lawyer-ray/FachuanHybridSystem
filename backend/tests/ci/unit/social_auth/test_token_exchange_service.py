"""social_auth token 交换与绑定列表服务单元测试。

覆盖一次性码无效/过期/账号未激活/成功四条路径与绑定账号列表，
失败路径必须保持 200 + success=False + message 契约（不抛异常）。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.organization.models import Lawyer
from apps.social_auth.models import SocialAccount, TempAuth
from apps.social_auth.services import exchange_temp_code_for_jwt, list_bound_accounts
from apps.social_auth.services.token_exchange_service import BoundAccountRow


@pytest.fixture
def lawyer(db: None) -> Lawyer:
    created: Lawyer = Lawyer.objects.create_user(username="tx_lawyer", password="x", real_name="张三")
    return created


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_invalid_code_returns_failure(lawyer: Lawyer) -> None:
    result = await exchange_temp_code_for_jwt("00000000-0000-0000-0000-000000000000")
    assert result.success is False
    assert result.message == "授权码无效或已过期"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_expired_code_is_deleted_and_rejected(lawyer: Lawyer) -> None:
    temp = await TempAuth.objects.acreate(user=lawyer)
    # created_at 由 auto_now_add 生成，直接回拨到 10 分钟前
    await TempAuth.objects.filter(pk=temp.pk).aupdate(created_at=timezone.now() - timedelta(minutes=10))

    result = await exchange_temp_code_for_jwt(temp.pk)
    assert result.success is False
    assert result.message == "授权码已过期，请重新扫码"
    assert await TempAuth.objects.filter(pk=temp.pk).aexists() is False


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_inactive_user_is_rejected(lawyer: Lawyer) -> None:
    temp = await TempAuth.objects.acreate(user=lawyer)
    await Lawyer.objects.filter(pk=lawyer.pk).aupdate(is_active=False)

    result = await exchange_temp_code_for_jwt(temp.pk)
    assert result.success is False
    assert result.message == "账号未激活，请联系管理员"
    assert await TempAuth.objects.filter(pk=temp.pk).aexists() is False


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_valid_code_exchanges_jwt_and_consumes_temp(lawyer: Lawyer) -> None:
    temp = await TempAuth.objects.acreate(user=lawyer)

    result = await exchange_temp_code_for_jwt(temp.pk)
    assert result.success is True
    assert result.access and result.refresh
    assert result.user_id == lawyer.id
    assert result.username == lawyer.username
    assert await TempAuth.objects.filter(pk=temp.pk).aexists() is False


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_bound_accounts_returns_rows_ordered(lawyer: Lawyer) -> None:
    await SocialAccount.objects.acreate(
        user=lawyer,
        provider="feishu",
        provider_uid="ou_1",
        display_name="张三",
        avatar_url="https://a/1.jpg",
        raw_profile={},
    )
    await SocialAccount.objects.acreate(
        user=lawyer,
        provider="dingtalk",
        provider_uid="dt_1",
        display_name="张三钉钉",
        avatar_url="",
        raw_profile={},
    )

    rows = await list_bound_accounts(lawyer)
    assert [r.provider for r in rows] == ["dingtalk", "feishu"]
    assert isinstance(rows[0], BoundAccountRow)
    assert rows[0].display_name == "张三钉钉"
    assert rows[1].bound_at  # bound_at 已格式化为 isoformat 字符串
