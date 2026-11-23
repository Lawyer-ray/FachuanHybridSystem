"""法规核查 / 能力检索的「自动挑本所威科凭证」路径。

## 这组测试守的是什么

`_resolve_credential_for()` 在 **async 视图**里被调用，而它内部要查
`AccountCredential.objects.filter(WEIKE_FILTER).first()`（同步 ORM）。一旦漏了
`sync_to_async`，Django 会抛 `SynchronousOnlyOperation`，端点恒 500。

2026-11-23 端到端实测踩到过：**任何挂着律所的真实律师、只要不传 `credential_id`
就 500**；只有 `law_firm_id is None` 的异常数据（resolver 提前 return None，不碰 DB）
才走到设计的 422 降级。所以这组用例直接打端点、断言状态码，把「async 上下文里调同步
ORM」这件事锁死。
"""

from __future__ import annotations

import pytest

from apps.organization.models import AccountCredential, Lawyer, LawFirm


def _make_firm_user(*, username: str, with_firm: bool = True) -> Lawyer:
    firm = LawFirm.objects.create(name=f"测试律所-{username}") if with_firm else None
    return Lawyer.objects.create(
        username=username,
        real_name=f"测试-{username}",
        law_firm=firm,
        is_superuser=False,
        is_staff=False,
    )


@pytest.mark.django_db
def test_law_verification_degrades_to_422_when_firm_has_no_weike_credential(client) -> None:
    """有律所、但本所没有威科凭证 → 必须是 422 降级，不能是 500。"""
    user = _make_firm_user(username="lr_no_cred")
    AccountCredential.objects.filter(lawyer__law_firm_id=user.law_firm_id).delete()

    client.force_login(user)
    resp = client.post(
        "/api/v1/legal-research/law-verification/check",
        data={"text": "根据《民法典》第874条，承运人应当承担责任。"},
        content_type="application/json",
    )

    assert resp.status_code == 422, resp.content
    assert "威科" in resp.content.decode()


@pytest.mark.django_db
def test_law_verification_resolves_firm_credential_without_explicit_id(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不传 credential_id、本所有凭证 → 应自动解析到该凭证并把请求交给服务层。

    这里不打真实威科：把服务层换成 stub，只断言「调用发生了」且状态码是 200。
    """
    user = _make_firm_user(username="lr_with_cred")
    # 字段以 apps/organization/models/credential.py 为准：WEIKE_FILTER 认 site_name 含
    # "weike"/"wkxx"/"wk" 或 url 含 wkinfo.com.cn 的凭证。
    credential = AccountCredential.objects.create(
        lawyer=user,
        site_name="weike",
        url="https://www.wkinfo.com.cn/",
        account="weike-user",
        password="weike-pass",
    )

    captured: dict[str, object] = {}

    class _StubLawVerificationService:
        def check_references(self, *, text: str, credential_id: int, user) -> dict[str, object]:
            captured["credential_id"] = credential_id
            captured["text"] = text
            return {"references": [], "total": 0}

    monkeypatch.setattr(
        "apps.legal_research.services.law_verification_service.LawVerificationService",
        _StubLawVerificationService,
    )

    client.force_login(user)
    resp = client.post(
        "/api/v1/legal-research/law-verification/check",
        data={"text": "根据《民法典》第874条，承运人应当承担责任。"},
        content_type="application/json",
    )

    assert resp.status_code == 200, resp.content
    assert captured["credential_id"] == credential.id


@pytest.mark.django_db
def test_law_verification_without_firm_still_degrades(client) -> None:
    """不挂律所的用户（异常数据）也要走 422 降级而不是报错。"""
    user = _make_firm_user(username="lr_no_firm", with_firm=False)

    client.force_login(user)
    resp = client.post(
        "/api/v1/legal-research/law-verification/check",
        data={"text": "根据《民法典》第874条。"},
        content_type="application/json",
    )

    assert resp.status_code == 422, resp.content
