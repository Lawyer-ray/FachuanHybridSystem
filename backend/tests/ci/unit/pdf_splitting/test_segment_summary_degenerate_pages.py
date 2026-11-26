"""分段阶段把取字阶段的 ``degenerate_pages`` 搬进 DB summary。

## 为什么需要这条用例

``degenerate_pages``（云端返回复读循环 / 空内容，被摘掉重取的页）原本只落
``analysis/extract_summary.json`` 这份磁盘侧车，``PdfSplitJob.summary_payload``
里没有。前端只读 summary，于是「哪几页云端给的内容是废的」这件事永远到不了
律师眼前——他只会看到某页正文少了或乱了，却没有任何可核对的提示。

这里用真库 + 真实 ``segment_stage`` 跑一遍：分段本身被替身成空结果，只验证
「侧车里的名单确实进了 summary_payload，且取字阶段已有的键不被抹掉」。

数据一律虚构；MEDIA_ROOT 隔离到 tmp_path（任务目录真的会读写）。
"""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitSourceType, PdfSplitStage
from apps.pdf_splitting.services.split import service as split_service
from apps.pdf_splitting.services.split import two_stage
from apps.pdf_splitting.services.split.pipeline import build_page_descriptor
from apps.pdf_splitting.services.storage import PdfSplitStorage

pytestmark = pytest.mark.django_db


@pytest.fixture
def _isolated_media_root(tmp_path: Path, settings: Any) -> Path:
    """隔离 MEDIA_ROOT：pages.json / extract_summary.json 都写在任务目录下。"""
    settings.MEDIA_ROOT = tmp_path / "media"
    return tmp_path


def _make_job() -> PdfSplitJob:
    return PdfSplitJob.objects.create(
        id=uuid4(),
        source_type=PdfSplitSourceType.UPLOAD,
        source_original_name="示例卷宗.pdf",
        status=PdfSplitJobStatus.PROCESSING,
        stage=PdfSplitStage.SEGMENT,
        total_pages=2,
        template_key="filing_materials_v1",
        # 取字阶段已经写下的键：分段阶段 merge_summary=False，必须保留
        summary_payload={"ocr_provider": "mineru"},
    )


def test_segment_stage_把degenerate_pages搬进summary(
    _isolated_media_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _make_job()
    storage = PdfSplitStorage(job.id)
    storage.ensure_dirs()
    two_stage.save_pages(
        storage,
        [
            build_page_descriptor(
                page_no=1,
                text="民事起诉状原告张三被告李四",
                source_method="mineru_ocr",
                ocr_failed=False,
                template_key="filing_materials_v1",
            ),
            build_page_descriptor(
                page_no=2,
                text="第二页正文",
                source_method="mineru_ocr",
                ocr_failed=False,
                template_key="filing_materials_v1",
            ),
        ],
    )
    # 取字阶段只把废页名单写进侧车文件；分段阶段必须把它搬进 summary_payload
    two_stage.save_extract_summary(storage, {"ocr_provider": "mineru", "degenerate_pages": [2]})

    # 分段本身不是这条用例的关注点：心跳线程与几何 pass 都替身掉，只留落库那一段
    monkeypatch.setattr(split_service, "periodic_heartbeat", lambda job_id: nullcontext())
    monkeypatch.setattr(split_service, "detect_segments_with_fallback", lambda *args, **kwargs: ([], {}))
    monkeypatch.setattr(split_service.PdfSplitService, "_ensure_table_geometry", lambda self, **kwargs: ({}, {}, {}))

    split_service.PdfSplitService().segment_stage(job)

    job.refresh_from_db()
    assert job.summary_payload["degenerate_pages"] == [2]
    # merge_summary=False：分段阶段只增不删，取字阶段写下的键必须还在
    assert job.summary_payload["ocr_provider"] == "mineru"
