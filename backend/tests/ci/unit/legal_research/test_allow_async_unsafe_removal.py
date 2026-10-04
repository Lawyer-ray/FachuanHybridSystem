"""删除 legal_research 三处 allow_async_unsafe 放行的回归测试。

同步 Playwright 的 _impl/_sync_base 在每次 sync 调用返回用户代码前执行
``asyncio._set_running_loop``，使执行线程长期挂着「运行中循环」——此后该线程
任何直连 sync ORM 都会抛 SynchronousOnlyOperation。历史上靠
allow_async_unsafe 环境变量压制；现在执行器/下载服务的全部 ORM 段经
``_run_orm_safely`` 摆渡到单 worker 线程执行，放行已删。

本文件用同一私有 API 复现 Playwright 的线程状态（比 mock
asyncio.get_running_loop 更接近真实：连 Django 的 ORM 探测都会命中），
证明：① 假循环下直连 ORM 确实会炸（环境 sanity，防止测试假绿）；
② 摆渡后的 _save_result / 下载结果落库在该环境下正常工作。
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import patch

import pytest
from django.core.exceptions import SynchronousOnlyOperation

from apps.legal_research.models import (
    CaseDownloadResult,
    CaseDownloadResultStatus,
    CaseDownloadTask,
    LegalResearchTask,
    LegalResearchTaskStatus,
)
from apps.legal_research.services.executor_components.result_persistence import ExecutorResultPersistenceMixin
from apps.legal_research.services.sources.base import CaseDetail
from apps.legal_research.services.task.case_download_service import CaseDownloadService
from apps.organization.models import AccountCredential
from apps.testing.factories import LawyerFactory


@contextmanager
def playwright_running_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """复现同步 Playwright 的 _set_running_loop 副作用，退出时还原。

    必须在 DB 造数完成之后进入（造数本身也要 ORM）。真 Playwright 的循环
    处于运行态（is_running()=True，_run_orm_safely 以此判定是否摆渡），
    new_event_loop() 造出的循环从未启动，需补标记运行态才是忠实复现。
    """
    loop = asyncio.new_event_loop()
    asyncio._set_running_loop(loop)
    try:
        # patch 随 yield 结束即退出，finally 里 close 时循环已恢复非运行态
        with patch.object(loop, "is_running", return_value=True):
            yield loop
    finally:
        asyncio._set_running_loop(None)
        loop.close()


def _make_credential() -> AccountCredential:
    lawyer = LawyerFactory()
    return AccountCredential.objects.create(
        lawyer=lawyer,
        site_name="weike",
        account=f"async_test_{lawyer.id}",
        password="test_password",
    )


def _make_detail() -> CaseDetail:
    # CaseDetail 是 Protocol（结构类型），按 cache_mixin 的既有范式用
    # SimpleNamespace 提供属性集
    return SimpleNamespace(  # type: ignore[return-value]
        doc_id_raw="raw-1",
        doc_id_unquoted="doc-1",
        detail_url="https://example.com/case/1",
        search_id="s1",
        module="cases",
        title="测试案例",
        court_text="测试法院",
        document_number="(2026)测001号",
        judgment_date="2026-01-01",
        case_digest="摘要",
        content_text="正文" * 100,
        raw_meta={},
    )


# transaction=True：摆渡线程用独立 DB 连接，须真实提交才能看到测试造的行
@pytest.mark.django_db(transaction=True)
class TestFakeLoopOrmFerry:
    def test_direct_orm_raises_under_fake_loop(self) -> None:
        """sanity：假循环下直连 ORM 必炸——证明测试环境真实复现了 Playwright 线程状态。"""
        with playwright_running_loop():
            with pytest.raises(SynchronousOnlyOperation):
                LegalResearchTask.objects.count()

    def test_save_result_ferried_under_fake_loop(self) -> None:
        """_save_result 在假循环下经摆渡正常落库（历史上是 allow_async_unsafe 的硬依赖）。"""
        cred = _make_credential()
        task = LegalResearchTask.objects.create(
            credential=cred,
            keyword="逾期利息",
            case_summary="借款合同纠纷",
            status=LegalResearchTaskStatus.RUNNING,
        )
        similarity = SimpleNamespace(score=0.87, reason="要素匹配", metadata={"k": "v"})

        with playwright_running_loop():
            ExecutorResultPersistenceMixin._save_result(
                task=task,
                detail=_make_detail(),
                similarity=similarity,
                rank=1,
                pdf=(b"%PDF-1.4 test", "测试案例.pdf"),
            )

        # 循环退出后校验（校验本身也走 ORM）
        from apps.legal_research.models import LegalResearchResult

        result = LegalResearchResult.objects.get(task=task, source_doc_id="doc-1")
        assert result.title == "测试案例"
        assert result.similarity_score == pytest.approx(0.87)
        assert result.pdf_file  # PDF 已随摆渡写入 storage

    def test_case_download_result_create_ferried_under_fake_loop(self) -> None:
        """_download_single_case 的结果落库在假循环下经摆渡正常工作。"""
        cred = _make_credential()
        lawyer = cred.lawyer
        task = CaseDownloadTask.objects.create(
            created_by=lawyer,
            credential=cred,
            case_numbers="(2026)测001号",
        )
        client = SimpleNamespace(search_cases=lambda **kwargs: [])  # 未找到案例 → FAILED 落库分支

        with playwright_running_loop():
            outcome = CaseDownloadService._download_single_case(
                client=client,  # type: ignore[arg-type]
                session=SimpleNamespace(close=lambda: None),  # type: ignore[arg-type]
                case_number="(2026)测001号",
                file_format="pdf",
                task=task,
            )

        assert outcome["success"] is False
        row = CaseDownloadResult.objects.get(task=task)
        assert row.status == CaseDownloadResultStatus.FAILED
        assert row.error_message == "未找到案例"
