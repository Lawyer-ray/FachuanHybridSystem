"""社交登录核心业务：按社交身份解析已绑定律师，以及账号绑定/解绑。

登录策略：**只放行已绑定的社交身份，绝不自动建号**。自动建出的 ``soc_xxx``
账号无法对应真实律师，管理员在后台无从判断「这条飞书记录是哪位律师」。
首次使用需先用账号密码登录，在「个人设置 → 账号绑定」完成绑定，见
``api/social_auth_api.py`` 的 bind-session 端点。

事务说明：Django（截至 6.1）的 ``transaction.atomic()`` 不支持
``async with``（不是 async context manager），直接在 async 函数里这样写
会在每次调用时抛 ``TypeError``。正确做法是把需要原子性的逻辑写成同步函数，
用 ``@transaction.atomic`` 装饰，再通过 ``sync_to_async`` 包装成异步接口。
"""

from __future__ import annotations

from asgiref.sync import sync_to_async
from django.db import transaction

from apps.organization.models import Lawyer
from apps.social_auth.models import SocialAccount

from ..providers.base import SocialProfile


class SocialAccountNotBoundError(Exception):
    """该社交身份尚未绑定任何律师账号，拒绝登录。"""


class SocialAccountConflictError(Exception):
    """该平台身份已绑定到另一位律师，不能重复绑定。"""


class SocialAccountProviderOccupiedError(Exception):
    """当前律师在该平台已绑定另一个账号，需先解绑再绑新的。"""


class SocialAccountNotFoundError(Exception):
    """要解绑的关联记录不存在。"""


def _refresh_profile(account: SocialAccount, profile: SocialProfile) -> None:
    """同步平台侧昵称/头像/原始数据，避免后台展示过期信息。"""
    if profile.display_name:
        account.display_name = profile.display_name
    if profile.avatar_url:
        account.avatar_url = profile.avatar_url
    account.raw_profile = profile.raw_data
    account.save()


@transaction.atomic
def _resolve_bound_user_sync(profile: SocialProfile) -> Lawyer:
    account = (
        SocialAccount.objects.select_related("user")
        .filter(provider=profile.provider, provider_uid=profile.provider_user_id)
        .first()
    )
    if account is None:
        raise SocialAccountNotBoundError(f"{profile.provider} 身份未绑定任何律师账号")

    _refresh_profile(account, profile)
    return account.user


async def resolve_user_by_social_profile(profile: SocialProfile) -> Lawyer:
    """按 (provider, provider_uid) 解析已绑定律师。

    未绑定时抛 ``SocialAccountNotBoundError``，由调用方转成前端可读提示。
    """
    return await sync_to_async(_resolve_bound_user_sync)(profile)


@transaction.atomic
def _bind_social_account_to_user_sync(profile: SocialProfile, user: Lawyer) -> SocialAccount:
    """把一个平台身份绑定到指定（已登录）律师。

    绝不新建 Lawyer，只做关联，并覆盖两种冲突：该身份已属于别人、
    以及该律师在此平台已有另一个账号。
    """
    existing = (
        SocialAccount.objects.select_related("user")
        .filter(provider=profile.provider, provider_uid=profile.provider_user_id)
        .first()
    )
    if existing:
        if existing.user_id != user.id:
            raise SocialAccountConflictError(f"该{profile.provider}账号已绑定其他律师")
        # 已绑定给自己：视为刷新资料，幂等处理
        _refresh_profile(existing, profile)
        return existing

    if SocialAccount.objects.filter(user=user, provider=profile.provider).exists():
        raise SocialAccountProviderOccupiedError(f"你已绑定该{profile.provider}平台的另一个账号，请先解绑")

    return SocialAccount.objects.create(
        user=user,
        provider=profile.provider,
        provider_uid=profile.provider_user_id,
        display_name=profile.display_name or "",
        avatar_url=profile.avatar_url or "",
        raw_profile=profile.raw_data,
    )


async def bind_social_account_to_user(profile: SocialProfile, user: Lawyer) -> SocialAccount:
    """``_bind_social_account_to_user_sync`` 的异步包装，供 async view 调用。"""
    return await sync_to_async(_bind_social_account_to_user_sync)(profile, user)


async def unbind_social_account(user: Lawyer, provider: str) -> None:
    """解除当前律师与某个平台的绑定。"""
    deleted, _ = await SocialAccount.objects.filter(user=user, provider=provider).adelete()
    if not deleted:
        raise SocialAccountNotFoundError(f"未找到 {provider} 的绑定记录")
