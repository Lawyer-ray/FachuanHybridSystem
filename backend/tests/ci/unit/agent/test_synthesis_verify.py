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


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_verify_degrades_without_weike_credential(firm_user) -> None:
    """没有威科凭证：不报错，返回"未配置"说明（律师才知道该去补账号，而不是以为查过有问题）。"""
    user, _lawyer = firm_user
    unverified, note = await verify_synthesis_citations(text="依据《民法典》第874条。", credential_id=None, user=user)
    assert unverified == []
    assert "威科" in note and "格式检查" in note


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_verify_never_reports_green_when_extraction_failed(firm_user, monkeypatch) -> None:
    """**防静默假绿**：核验返回 0 条、但本地能抽出引用 → 必须报"未核验"。

    2026-11-22 实测事故：模型把条号写成「第 874 条」（带空格），旧抽取正则一条
    都认不出，核验返回 0 条，上层于是当作"文里没有法规引用"，`unverified` 空着
    ——律师看到的是"全部通过"，实际一条都没核。
    """
    from asgiref.sync import sync_to_async

    from apps.legal_research.services import law_verification_service as svc_module
    from apps.organization.models import AccountCredential

    user, lawyer = firm_user
    await sync_to_async(AccountCredential.objects.create)(
        lawyer=lawyer, site_name="威科", url="https://www.wkinfo.com.cn/login/index", account="a"
    )

    class _EmptyService:
        def check_references(self, *, text: str, credential_id: int, user):
            return {"references": [], "total": 0}

    monkeypatch.setattr(svc_module, "LawVerificationService", _EmptyService)

    unverified, note = await verify_synthesis_citations(
        text="依据《民法典》第 874 条，受让人按约定实施…", credential_id=None, user=user
    )
    assert unverified, "抽到引用但核验没返回时必须报未核验，不能空着"
    assert "未核验" in unverified[0]
    assert "抽出 1 条引用" in note


def test_statute_regex_accepts_spaces_around_article() -> None:
    """「第 874 条」带空格是模型的常见写法，抽取器必须认。"""
    from apps.agent.services.chat.citation_check import extract_statute_refs

    refs = extract_statute_refs("依据《民法典》第 874 条、《刑法》第285条第3款。")
    assert [r.law_name for r in refs] == ["民法典", "刑法"]


def test_normalize_article_spacing() -> None:
    from apps.legal_research.services.law_verification_service import normalize_article_spacing

    assert normalize_article_spacing("第 874 条") == "第874条"
    assert normalize_article_spacing("第874条") == "第874条"
    assert normalize_article_spacing("第 1 条、第 874 条") == "第1条、第874条"
