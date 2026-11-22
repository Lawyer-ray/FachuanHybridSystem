"""综合稿引用核验：凭证**自动解析**（不让调用方猜 ID）+ 无凭证时的降级口径。

`AccountCredential` 一张表里混着法院送达 / OA / 工商 / 邮箱 / 威科，所以
「请传入 credential_id」对律师和模型都是不可解的问题。本文件钉住三条：

1. 解析只认威科（url 含 wkinfo / 站点名 wkxx / wk / weike），别把工商账号当威科；
2. 显式指定的 ID 原样透传，不做二次猜测；
3. 一条威科凭证都没有时，核验**降级为"只做格式检查"并说明原因**，而不是报错
   ——综合稿本身有价值，核验不了不该把它一起丢掉。
"""

from __future__ import annotations

import uuid

import pytest

from apps.agent.services.synthesis.verify import verify_synthesis_citations
from apps.legal_research.services.credential_resolver import resolve_weike_credential_id


@pytest.fixture
def firm_user(db):
    from django.contrib.auth import get_user_model

    from apps.organization.models import LawFirm, Lawyer

    firm = LawFirm.objects.create(name="测试律所")
    lawyer = Lawyer.objects.create(real_name="测试律师", law_firm=firm)
    user = get_user_model().objects.create(username=f"u-{uuid.uuid4().hex[:8]}")
    user.law_firm = firm
    user.save(update_fields=["law_firm"])
    return user, lawyer


@pytest.mark.django_db
def test_resolver_picks_only_weike_credential(firm_user) -> None:
    from apps.organization.models import AccountCredential

    user, lawyer = firm_user
    AccountCredential.objects.create(lawyer=lawyer, site_name="工商", url="https://shiming.gsxt.gov.cn/")
    weike = AccountCredential.objects.create(
        lawyer=lawyer, site_name="威科", url="https://www.wkinfo.com.cn/login/index", account="a"
    )

    assert resolve_weike_credential_id(user=user) == weike.id


@pytest.mark.django_db
def test_resolver_passthrough_explicit(firm_user) -> None:
    user, _lawyer = firm_user
    assert resolve_weike_credential_id(user=user, explicit=7) == 7


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_verify_degrades_without_weike_credential(firm_user) -> None:
    """没有威科凭证：不报错，返回"未配置"说明（律师才知道该去补账号，而不是以为查过有问题）。"""
    user, _lawyer = firm_user
    unverified, note = await verify_synthesis_citations(text="依据《民法典》第874条。", credential_id=None, user=user)
    assert unverified == []
    assert "威科" in note and "格式检查" in note
