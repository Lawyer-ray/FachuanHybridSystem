"""`PdfSplitJobService.confirm_segments` 与 `_normalize_confirmed_segments` 的单测。

## 这些用例存在的原因

`confirm_segments` 是「律师人工确认分段 → 落库 → 排导出任务」的唯一入口。它此前
带着一条写在 def 行尾的 ``# pragma: no cover``（coverage 只排除 def 行，函数体
照算未覆盖），后来 pragma 被清掉，于是它成为 `job_service.py` 最后一个真缺口。

它值得测的理由不是「提高数字」，而是这几条**错了会直接产出坏卷宗**的规则：

* **页码越界/重叠必须拒** —— 放过去就是同一页被分到两份材料里，或者索引越界；
* **缺页要自动补一段 `未识别材料_起-止`** —— 静默丢页是最坏的失败模式：律师看到
  「导出成功」，卷宗却少了几页；
* **未识别类型的文件名要兜底** —— 空文件名落进导出环节会生成无意义的文件；
* 确认后任务必须进入 ``EXPORTING`` 并排进队列 —— 否则律师点了确认什么也不会发生。

测试数据（文件名、正文）全部虚构；MEDIA_ROOT 隔离到 tmp_path（``write_json``
会真的往任务目录写 ``segments.json``）。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from apps.core.exceptions import ValidationException
from apps.pdf_splitting.models import (
    PdfSplitJob,
    PdfSplitJobStatus,
    PdfSplitReviewFlag,
    PdfSplitSegment,
    PdfSplitSegmentType,
    PdfSplitSourceType,
)
from apps.pdf_splitting.services.job_service import PdfSplitJobService

pytestmark = pytest.mark.django_db

_SUBMIT_PATH = "apps.pdf_splitting.services.job_service.build_task_submission_service"


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path: Path, settings: Any) -> Path:
    """确认分段会写 ``segments.json`` 到任务目录，必须隔离 MEDIA_ROOT。"""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def _job(*, pages: int = 5, status: str = PdfSplitJobStatus.REVIEW_REQUIRED) -> PdfSplitJob:
    return PdfSplitJob.objects.create(
        id=uuid.uuid4(),
        source_type=PdfSplitSourceType.UPLOAD,
        source_original_name="确认分段示例.pdf",
        status=status,
        total_pages=pages,
    )


def _item(
    page_start: int,
    page_end: int,
    *,
    segment_type: str = PdfSplitSegmentType.COMPLAINT,
    filename: str = "",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "page_start": page_start,
        "page_end": page_end,
        "segment_type": segment_type,
        "filename": filename,
        **extra,
    }


class TestNormalizeRejects:
    """非法输入必须在落库之前被挡住——这些一旦放过去就是坏卷宗。"""

    def test_空列表被拒(self) -> None:
        with pytest.raises(ValidationException, match="至少保留一个片段"):
            PdfSplitJobService()._normalize_confirmed_segments(items=[], total_pages=5)

    @pytest.mark.parametrize("bad", ["第一页", None, "1.5"])
    def test_页码非整数被拒(self, bad: Any) -> None:
        """页码来自前端 JSON，字符串/None/小数都可能混进来。"""
        item = {"page_start": bad, "page_end": 2, "segment_type": "complaint", "filename": "a.pdf"}
        with pytest.raises(ValidationException, match="页码必须为整数"):
            PdfSplitJobService()._normalize_confirmed_segments(items=[item], total_pages=5)

    @pytest.mark.parametrize(
        ("start", "end"),
        [(0, 2), (3, 2), (1, 99)],
        ids=["起点小于1", "终点小于起点", "终点超过总页数"],
    )
    def test_页码范围非法被拒(self, start: int, end: int) -> None:
        with pytest.raises(ValidationException, match="页码非法"):
            PdfSplitJobService()._normalize_confirmed_segments(items=[_item(start, end)], total_pages=5)

    def test_重叠被拒(self) -> None:
        """两段共用同一页 → 同一页会被导出进两份材料，必须拒。"""
        items = [_item(1, 3), _item(3, 5)]
        with pytest.raises(ValidationException, match="重叠"):
            PdfSplitJobService()._normalize_confirmed_segments(items=items, total_pages=5)


class TestNormalizeFillsGaps:
    """缺页自动补段——静默丢页是最坏的失败模式。"""

    def test_中间缺口被补成未识别材料(self) -> None:
        filled = PdfSplitJobService()._normalize_confirmed_segments(items=[_item(1, 2), _item(5, 5)], total_pages=5)

        assert [(i["page_start"], i["page_end"]) for i in filled] == [(1, 2), (3, 4), (5, 5)]
        gap = filled[1]
        assert gap["segment_type"] == PdfSplitSegmentType.UNRECOGNIZED
        assert gap["filename"] == "未识别材料_3-4.pdf"
        assert gap["source_method"] == "gap_fill"
        assert gap["review_flag"] == PdfSplitReviewFlag.UNRECOGNIZED

    def test_尾部缺口被补到总页数(self) -> None:
        filled = PdfSplitJobService()._normalize_confirmed_segments(items=[_item(1, 3)], total_pages=5)
        assert filled[-1]["page_end"] == 5
        assert filled[-1]["filename"] == "未识别材料_4-5.pdf"

    def test_头部缺口也会补(self) -> None:
        filled = PdfSplitJobService()._normalize_confirmed_segments(items=[_item(3, 5)], total_pages=5)
        assert filled[0]["page_start"] == 1
        assert filled[0]["page_end"] == 2

    def test_无缺口时不补(self) -> None:
        filled = PdfSplitJobService()._normalize_confirmed_segments(items=[_item(1, 5)], total_pages=5)
        assert len(filled) == 1
        assert all(i["source_method"] != "gap_fill" for i in filled)

    def test_输出按页码排序(self) -> None:
        filled = PdfSplitJobService()._normalize_confirmed_segments(items=[_item(4, 5), _item(1, 2)], total_pages=5)
        starts = [i["page_start"] for i in filled]
        assert starts == sorted(starts)


class TestNormalizeDefaults:
    """文件名与类型的兜底——空文件名落进导出环节会生成无意义的文件。"""

    def test_空文件名按类型兜底并补pdf后缀(self) -> None:
        filled = PdfSplitJobService()._normalize_confirmed_segments(
            items=[_item(1, 5, segment_type=PdfSplitSegmentType.COMPLAINT)], total_pages=5
        )
        name = filled[0]["filename"]
        assert name.endswith(".pdf"), name
        assert name, "不能留空文件名"

    def test_未识别类型文件名带页码(self) -> None:
        """未识别段的文件名必须带自己的页码区间，否则导出后无从分辨哪段是哪几页。

        注意取「输入那一段」而不是 filled[0]：第 1 页与第 5 页都是缺口，会被
        自动补段，filled[0] 其实是补出来的「未识别材料_1-1.pdf」。
        """
        filled = PdfSplitJobService()._normalize_confirmed_segments(
            items=[_item(2, 4, segment_type=PdfSplitSegmentType.UNRECOGNIZED)], total_pages=5
        )
        mine = [i for i in filled if i["source_method"] != "gap_fill"]
        assert len(mine) == 1
        assert "2-4" in mine[0]["filename"]
        assert mine[0]["review_flag"] == PdfSplitReviewFlag.UNRECOGNIZED

    def test_非法类型落回未识别(self) -> None:
        """前端传了个不存在的类型时，不能把它原样落库。"""
        filled = PdfSplitJobService()._normalize_confirmed_segments(
            items=[_item(1, 5, segment_type="不存在的类型")], total_pages=5
        )
        assert filled[0]["segment_type"] == PdfSplitSegmentType.UNRECOGNIZED

    def test_缺pdf后缀会被补上(self) -> None:
        filled = PdfSplitJobService()._normalize_confirmed_segments(
            items=[_item(1, 5, filename="起诉状")], total_pages=5
        )
        assert filled[0]["filename"].lower().endswith(".pdf")


class TestConfirmSegments:
    """端到端：确认后 DB 段、segments.json、任务状态三者必须一致。"""

    def test_确认后落库并排导出(self, tmp_path: Path) -> None:
        job = _job(pages=4)
        with patch(_SUBMIT_PATH) as submit:
            submit.return_value.submit.return_value = "task-xyz"

            result = PdfSplitJobService().confirm_segments(
                job_id=job.id,
                items=[_item(1, 2, filename="起诉状.pdf"), _item(3, 4, filename="证据.pdf")],
            )

        # 1) DB 段
        segments = list(PdfSplitSegment.objects.filter(job=job).order_by("order"))
        assert [(s.page_start, s.page_end) for s in segments] == [(1, 2), (3, 4)]
        assert [s.order for s in segments] == [1, 2]

        # 2) 落盘的 segments.json 与 DB 一致
        json_path = tmp_path / "pdf_splitting" / "jobs" / str(job.id) / "analysis" / "segments.json"
        assert json_path.exists(), "导出任务读的是这份文件，没写就等于没确认"
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert len(payload) == 2

        # 3) 任务进入 EXPORTING 且拿到 task_id
        assert result.status == PdfSplitJobStatus.EXPORTING
        assert result.task_id == "task-xyz"
        assert result.cancel_requested is False

    def test_重复确认会覆盖旧段而不是累加(self) -> None:
        """律师改完分段再点一次确认，旧段必须被替换——累加会产出重复页。

        关键：第一次确认会把任务推进到 EXPORTING，而 EXPORTING 不在允许确认的
        状态集里（PENDING/CANCELLED 那一类也会被同样拒掉）。所以第二次确认前
        必须把状态退回 REVIEW_REQUIRED——这也正是真实流程的形态：导出完成后
        任务回到待复核，律师才能再改。
        """
        job = _job(pages=4)
        service = PdfSplitJobService()
        with patch(_SUBMIT_PATH) as submit:
            submit.return_value.submit.return_value = "t1"
            service.confirm_segments(job_id=job.id, items=[_item(1, 4, filename="旧.pdf")])

            # 模拟导出完成、回到待复核
            PdfSplitJob.objects.filter(id=job.id).update(status=PdfSplitJobStatus.REVIEW_REQUIRED)

            service.confirm_segments(
                job_id=job.id,
                items=[_item(1, 2, filename="新A.pdf"), _item(3, 4, filename="新B.pdf")],
            )

        segments = list(PdfSplitSegment.objects.filter(job=job).order_by("order"))
        assert len(segments) == 2, "旧的 1 段应被删掉，只剩新的 2 段"
        assert {s.filename for s in segments} == {"新A.pdf", "新B.pdf"}

    def test_导出中不允许再次确认(self) -> None:
        """EXPORTING 期间再确认会把正在导出的任务搞乱，必须拒。"""
        job = _job(pages=4, status=PdfSplitJobStatus.EXPORTING)
        with pytest.raises(ValidationException, match="不允许确认导出"):
            PdfSplitJobService().confirm_segments(job_id=job.id, items=[_item(1, 4)])

    @pytest.mark.parametrize("status", [PdfSplitJobStatus.PENDING, PdfSplitJobStatus.CANCELLED])
    def test_状态不允许时拒绝确认(self, status: str) -> None:
        """PENDING（还没跑）与 CANCELLED（已放弃）都不该能确认导出。"""
        job = _job(pages=4, status=status)
        with pytest.raises(ValidationException, match="不允许确认导出"):
            PdfSplitJobService().confirm_segments(job_id=job.id, items=[_item(1, 4)])
        assert not PdfSplitSegment.objects.filter(job=job).exists(), "被拒时不该留下半成品"

    def test_已完成的也能再次确认(self) -> None:
        """COMPLETED 状态允许重新确认（律师可能改主意再拆一次）。"""
        job = _job(pages=4, status=PdfSplitJobStatus.COMPLETED)
        with patch(_SUBMIT_PATH) as submit:
            submit.return_value.submit.return_value = "t2"
            result = PdfSplitJobService().confirm_segments(job_id=job.id, items=[_item(1, 4)])
        assert result.status == PdfSplitJobStatus.EXPORTING
