"""综合稿引用核验：凭证**自动解析**（不让调用方猜 ID）+ 无凭证时的降级口径。

`AccountCredential` 一张表里混着法院送达 / OA / 工商 / 邮箱 / 威科，所以
「请传入 credential_id」对律师和模型都是不可解的问题。本文件钉住三条：

1. 解析只认威科（url 含 wkinfo / 站点名 wkxx / wk / weike），别把工商账号当威科；
2. 显式指定的 ID 原样透传，不做二次猜测；
3. 一条威科凭证都没有时，核验**降级为"只做格式检查"并说明原因**，而不是报错
   ——综合稿本身有价值，核验不了不该把它一起丢掉。
"""

from __future__ import annotations

import asyncio
import threading
import uuid

import pytest

from apps.agent.services.synthesis.verify import verify_synthesis_citations
from apps.legal_research.services.credential_resolver import resolve_weike_credential_id


@pytest.fixture
def firm_user(transactional_db):
    """律所 + 律师 + 用户，**提交可见**（`transactional_db`，不是 `db`）。

    为什么必须是事务模式而不是 `db`：本文件的异步用例会在 `sync_to_async` 里读库，
    那是**另一条数据库连接**。非事务模式下 fixture 的数据还在未提交的事务里，另一条
    连接看不到它（如果那条连接还要写外键，就会直接报 `ForeignKeyViolation`——机制已用
    探针实测：同一份数据 `db` 下必报、`transactional_db` 下正常）。

    改成 fixture 直接要 `transactional_db`，比依赖用例上的
    `@pytest.mark.django_db(transaction=True)` 更稳：pytest-django 只要在 fixturenames
    里看到 `transactional_db` 就走 `TransactionTestCase`（fixtures.py `_django_db_helper`），
    因此新增用例忘了写 marker 也不会退化成“看不到 fixture 数据”。
    """
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
    from apps.agent.services.synthesis import verify as verify_module
    from apps.legal_research.services import law_verification_service as svc_module

    user, _lawyer = firm_user

    # 凭证解析直接打桩：本用例验的是「核验返回 0 条 ≠ 全部通过」，不需要真的在库里
    # 建一条威科账号。顺带把「异步用例在另一条连接上**写库**」这条路去掉——那条路
    # 是 2026-11-22 那个偶发外键违规的唯一写入口（详见本文件 ``firm_user`` 的注释）。
    monkeypatch.setattr(verify_module, "resolve_weike_credential_id", lambda **_kwargs: 42)

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


# ── 执行方式与取消（评审 🔴4 / 🔴6）────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_references_runs_off_the_shared_sync_thread(monkeypatch) -> None:
    """威科核验不能占 asgiref 的全局同步线程（``thread_sensitive=True``），且用完关连接。

    旧实现 ``sync_to_async(check_references, thread_sensitive=True)``：一次几分钟的
    威科登录 + 核查期间，全进程所有 thread_sensitive 的同步 ORM 都得排队。
    """
    from apps.agent.services.synthesis import verify as verify_module
    from apps.legal_research.services import law_verification_service as svc_module

    seen: dict[str, str] = {}

    class _RecordingService:
        def check_references(self, *, text: str, credential_id: int, user):
            seen["call_thread"] = threading.current_thread().name
            return {"references": [{"law_name": "民法典", "article_num": 874, "status": "valid"}]}

    class _RecordingConnections:
        def close_all(self) -> None:
            seen["close_thread"] = threading.current_thread().name

    monkeypatch.setattr(verify_module, "resolve_weike_credential_id", lambda **_kwargs: 42)
    monkeypatch.setattr(verify_module, "connections", _RecordingConnections())
    monkeypatch.setattr(svc_module, "LawVerificationService", _RecordingService)

    unverified, note = await verify_synthesis_citations(text="依据《民法典》第874条。", credential_id=None, user=None)

    assert (unverified, note) == ([], "")
    assert seen["call_thread"].startswith(verify_module.VERIFY_THREAD_PREFIX)
    # 连接按线程持有：必须在**同一个**核验线程里关掉
    assert seen["close_thread"] == seen["call_thread"]


@pytest.mark.asyncio
async def test_cancellation_is_not_swallowed_as_verify_failure(monkeypatch) -> None:
    """取消不是"核验失败"：旧实现把 CancelledError 接住并返回「核验未执行」，综合随后照常落库。"""
    from apps.agent.services.synthesis import verify as verify_module
    from apps.legal_research.services import law_verification_service as svc_module

    started = threading.Event()
    release = threading.Event()

    class _BlockingService:
        def check_references(self, *, text: str, credential_id: int, user):
            started.set()
            release.wait(timeout=5)
            return {"references": []}

    monkeypatch.setattr(verify_module, "resolve_weike_credential_id", lambda **_kwargs: 42)
    monkeypatch.setattr(svc_module, "LawVerificationService", _BlockingService)

    task = asyncio.ensure_future(
        verify_synthesis_citations(text="依据《民法典》第874条。", credential_id=None, user=None)
    )
    try:
        for _ in range(200):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set(), "核验线程没有启动"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()


@pytest.mark.asyncio
async def test_ordinary_verify_failure_still_degrades(monkeypatch) -> None:
    """普通异常仍按"核验未执行"降级，不阻断综合（取消之外的口径不变）。"""
    from apps.agent.services.synthesis import verify as verify_module
    from apps.legal_research.services import law_verification_service as svc_module

    class _BrokenService:
        def check_references(self, *, text: str, credential_id: int, user):
            raise RuntimeError("威科登录失败")

    monkeypatch.setattr(verify_module, "resolve_weike_credential_id", lambda **_kwargs: 42)
    monkeypatch.setattr(svc_module, "LawVerificationService", _BrokenService)

    unverified, note = await verify_synthesis_citations(text="依据《民法典》第874条。", credential_id=None, user=None)
    assert unverified == []
    assert note == "核验未执行：RuntimeError"
