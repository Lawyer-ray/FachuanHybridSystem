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
* 确认后任务必须进入 ``EXPORTING`` 并排进队列 —— 否则律师点了确认什么也不会发生；
* **``segments_md.json`` 必须按确认后的页区间重写** —— 只写 ``segments.json`` 会让
  ``content_md`` 整体错位一格（md 按旧 order 存、DB 段按 1 基重建），且律师合并/拆分
  分段后旧 md 与新区间根本对不上。见 ``TestConfirmRewritesMarkdown``。

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

    def test_确认后落库并排导出(self, tmp_path: Path, django_capture_on_commit_callbacks: Any) -> None:
        job = _job(pages=4)
        with patch(_SUBMIT_PATH) as submit:
            submit.return_value.submit.return_value = "task-xyz"

            # G7（2026-11-23 二轮审计）：导出任务改为 `transaction.on_commit` 派发
            # （原实现写在 atomic 内，worker 可能读到删前/建前的分段 → 导出错包）。
            # 单测里必须显式执行 on_commit 回调，否则任务永远不会被派发。
            with django_capture_on_commit_callbacks(execute=True):
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

        # 3) 任务进入 EXPORTING；task_id 在事务提交后才回写（on_commit 内），故查库而非查返回对象
        assert result.status == PdfSplitJobStatus.EXPORTING
        assert result.cancel_requested is False
        job.refresh_from_db()
        assert job.task_id == "task-xyz"

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


# ── confirm 后 content_md 必须与段一致（P0-3）──────────────────────────
#
# 病因：md 产物按**旧** order 存（LLM 路径 0 基），confirm 按 1 基重建 DB 段却
# 只写 segments.json。读取侧拿 1 基查 0 基字典 → 每段拿到上一段正文、末段空串。
#
# ⚠️ 验收口径（分析报告 §4 / §9.1）：**必须覆盖真的调整过分段的情形**，不能只测
# 「什么都没改直接确认」——只统一 order 基址也能让那条绿，而律师一合并/拆分就又错。


def _page_payload(page_no: int, *, layout: dict[str, Any] | None = None) -> dict[str, Any]:
    text = f"第{page_no}页正文"
    return {
        "page_no": page_no,
        "text": text,
        "normalized_text": text,
        "head_text": text,
        "source_method": "fast_text",
        "ocr_failed": False,
        "top_candidates": [],
        "layout": layout,
        "layout_title": "",
    }


def _seed_products(
    job: PdfSplitJob,
    *,
    with_pages: bool = True,
    md_entries: list[dict[str, Any]] | None = None,
    extract_summary: dict[str, Any] | None = None,
    layouts: dict[int, dict[str, Any]] | None = None,
) -> Any:
    """铺一份「自动分段跑完」的任务目录产物。"""
    from apps.pdf_splitting.services.storage import PdfSplitStorage

    storage = PdfSplitStorage(job.id)
    storage.ensure_dirs()
    if with_pages:
        pages = [_page_payload(no, layout=(layouts or {}).get(no)) for no in range(1, job.total_pages + 1)]
        storage.write_json(storage.pages_json_path, pages)
    if extract_summary is not None:
        storage.write_json(storage.extract_summary_json_path, extract_summary)
    if md_entries is not None:
        storage.write_json(storage.segments_md_path, md_entries)
    return storage


def _old_md_entries(ranges: list[tuple[int, int]]) -> list[dict[str, Any]]:
    """旧 md 产物：**0 基 order**（segment_batch.merge_batch_drafts 的真实形态）。"""
    return [
        {
            "order": index,
            "page_start": start,
            "page_end": end,
            "markdown": f"# 旧名{index}\n\n" + "\n\n".join(f"第{no}页正文" for no in range(start, end + 1)),
            "positioned": [],
            "quality_flags": [],
        }
        for index, (start, end) in enumerate(ranges)
    ]


def _confirmed_payload(job: PdfSplitJob, items: list[dict[str, Any]]) -> dict[str, Any]:
    """确认 → 读回任务详情（前端与 MCP 拿到的就是这份）。"""
    service = PdfSplitJobService()
    with patch(_SUBMIT_PATH) as submit:
        submit.return_value.submit.return_value = "task-confirm"
        service.confirm_segments(job_id=job.id, items=items)
    job.refresh_from_db()
    return service.build_job_payload(job)


def _assert_segment_md(segment: dict[str, Any], *, total_pages: int) -> None:
    start, end = segment["page_start"], segment["page_end"]
    markdown = segment["content_md"]
    assert markdown.strip(), f"第 {start}-{end} 页这段正文为空（错位一格的末段症状）"
    for no in range(1, total_pages + 1):
        if start <= no <= end:
            assert f"第{no}页正文" in markdown, f"段 {start}-{end} 缺第 {no} 页"
        else:
            assert f"第{no}页正文" not in markdown, f"段 {start}-{end} 混进第 {no} 页（错位一格）"


class TestConfirmRewritesMarkdown:
    """确认后 content_md 必须按**确认后的页区间**重建。"""

    def test_什么都没改直接确认也不再有错位一格(self) -> None:
        job = _job(pages=6)
        _seed_products(job, md_entries=_old_md_entries([(1, 2), (3, 4), (5, 6)]))

        payload = _confirmed_payload(
            job,
            [
                _item(1, 2, filename="起诉状.pdf", segment_type=PdfSplitSegmentType.COMPLAINT),
                _item(3, 4, filename="证据一.pdf"),
                _item(5, 6, filename="证据二.pdf"),
            ],
        )

        segments = payload["segments"]
        assert [s["order"] for s in segments] == [1, 2, 3]
        for segment in segments:
            _assert_segment_md(segment, total_pages=6)

    def test_合并两段后正文覆盖合并区间(self) -> None:
        job = _job(pages=6)
        _seed_products(job, md_entries=_old_md_entries([(1, 2), (3, 4), (5, 6)]))

        payload = _confirmed_payload(job, [_item(1, 4, filename="合并.pdf"), _item(5, 6, filename="尾段.pdf")])

        assert len(payload["segments"]) == 2
        for segment in payload["segments"]:
            _assert_segment_md(segment, total_pages=6)

    def test_拆分一段后两半各拿自己那几页(self) -> None:
        job = _job(pages=4)
        _seed_products(job, md_entries=_old_md_entries([(1, 4)]))

        payload = _confirmed_payload(job, [_item(1, 2, filename="前半.pdf"), _item(3, 4, filename="后半.pdf")])

        assert [(s["page_start"], s["page_end"]) for s in payload["segments"]] == [(1, 2), (3, 4)]
        for segment in payload["segments"]:
            _assert_segment_md(segment, total_pages=4)

    def test_改页区间后补洞段也有正文(self) -> None:
        """律师把边界挪到 2-3：头尾缺口被补成未识别段，它们同样不能是空的。"""
        job = _job(pages=4)
        _seed_products(job, md_entries=_old_md_entries([(1, 4)]))

        payload = _confirmed_payload(job, [_item(2, 3, filename="挪过边界.pdf")])

        assert [(s["page_start"], s["page_end"]) for s in payload["segments"]] == [(1, 1), (2, 3), (4, 4)]
        for segment in payload["segments"]:
            _assert_segment_md(segment, total_pages=4)

    def test_改名后段标题跟着变(self) -> None:
        job = _job(pages=2)
        _seed_products(job, md_entries=_old_md_entries([(1, 2)]))

        payload = _confirmed_payload(job, [_item(1, 2, filename="律师改过的名字.pdf")])

        assert payload["segments"][0]["content_md"].startswith("# 律师改过的名字\n")

    def test_输入乱序时正文仍按页序对齐(self) -> None:
        job = _job(pages=4)
        _seed_products(job, md_entries=_old_md_entries([(1, 2), (3, 4)]))

        payload = _confirmed_payload(job, [_item(3, 4, filename="乙.pdf"), _item(1, 2, filename="甲.pdf")])

        assert payload["segments"][0]["content_md"].startswith("# 甲\n")
        for segment in payload["segments"]:
            _assert_segment_md(segment, total_pages=4)

    def test_重复确认按最后一次的区间重建(self) -> None:
        """第二次确认不能沿用第一次的 md——那正是「改完还是旧正文」的形态。"""
        job = _job(pages=4)
        _seed_products(job, md_entries=_old_md_entries([(1, 4)]))
        service = PdfSplitJobService()
        with patch(_SUBMIT_PATH) as submit:
            submit.return_value.submit.return_value = "t"
            service.confirm_segments(job_id=job.id, items=[_item(1, 4, filename="整本.pdf")])
            PdfSplitJob.objects.filter(id=job.id).update(status=PdfSplitJobStatus.REVIEW_REQUIRED)
            service.confirm_segments(
                job_id=job.id, items=[_item(1, 1, filename="甲.pdf"), _item(2, 4, filename="乙.pdf")]
            )
        job.refresh_from_db()

        segments = service.build_job_payload(job)["segments"]
        assert [(s["page_start"], s["page_end"]) for s in segments] == [(1, 1), (2, 4)]
        for segment in segments:
            _assert_segment_md(segment, total_pages=4)

    def test_坐标按取字落盘的实际平台换算而不是auto(self) -> None:
        """job.cloud_backend 默认 auto → 单位 unknown → positioned 恒空（原 bug）。"""
        job = _job(pages=1)
        layout = {"blocks": [{"type": "text", "text": "第1页正文", "bbox": [100, 100, 500, 200]}]}
        _seed_products(
            job,
            layouts={1: layout},
            extract_summary={"ocr_provider": "mineru", "cloud_failover_from": ["textin"]},
            md_entries=_old_md_entries([(1, 1)]),
        )
        assert job.cloud_backend == "auto"

        payload = _confirmed_payload(job, [_item(1, 1, filename="有坐标.pdf")])

        assert payload["segments"][0]["positioned"], "实际平台是 mineru，坐标必须能算出来"

    def test_旧任务没有取字摘要时正文仍正确(self) -> None:
        """坐标降级为不可用是可以接受的；正文错位不可以。"""
        job = _job(pages=2)
        _seed_products(job, md_entries=_old_md_entries([(1, 2)]))

        payload = _confirmed_payload(job, [_item(1, 2, filename="旧任务.pdf")])

        _assert_segment_md(payload["segments"][0], total_pages=2)
        assert payload["segments"][0]["positioned"] == []

    def test_每段都带page_spans字段(self) -> None:
        """字段形状契约：前端按 page_spans 映射 pageSpans，缺键会 undefined。"""
        job = _job(pages=2)
        _seed_products(job, md_entries=_old_md_entries([(1, 2)]))

        payload = _confirmed_payload(job, [_item(1, 2, filename="锚点.pdf")])

        assert isinstance(payload["segments"][0]["page_spans"], list)

    def test_页锚点切出来的正是本页正文(self) -> None:
        """confirm 重建后锚点必须按**新** md 算——前端切/并段就靠它精确切分。"""
        job = _job(pages=4)
        _seed_products(job, md_entries=_old_md_entries([(1, 4)]))

        payload = _confirmed_payload(job, [_item(1, 2, filename="前半.pdf"), _item(3, 4, filename="后半.pdf")])

        for segment in payload["segments"]:
            spans = segment["page_spans"]
            assert [span["page"] for span in spans] == list(range(segment["page_start"], segment["page_end"] + 1))
            for span in spans:
                assert f"第{span['page']}页正文" in segment["content_md"][span["start"] : span["end"]]


class TestConfirmMarkdownWithoutPages:
    """旧任务 pages.json 缺失/损坏时按页区间重新配对，**不许静默错位**。"""

    def test_没有pages_json时页区间没变的段仍对得上(self) -> None:
        job = _job(pages=6)
        _seed_products(job, with_pages=False, md_entries=_old_md_entries([(1, 2), (3, 4), (5, 6)]))

        payload = _confirmed_payload(
            job, [_item(1, 2, filename="甲.pdf"), _item(3, 4, filename="乙.pdf"), _item(5, 6, filename="丙.pdf")]
        )

        assert [(s["page_start"], s["page_end"]) for s in payload["segments"]] == [(1, 2), (3, 4), (5, 6)]
        for segment in payload["segments"]:
            _assert_segment_md(segment, total_pages=6)

    def test_没有pages_json时合并段按页序拼接(self) -> None:
        job = _job(pages=4)
        _seed_products(job, with_pages=False, md_entries=_old_md_entries([(1, 2), (3, 4)]))

        payload = _confirmed_payload(job, [_item(1, 4, filename="合并.pdf")])

        markdown = payload["segments"][0]["content_md"]
        assert markdown.index("第1页正文") < markdown.index("第3页正文")
        _assert_segment_md(payload["segments"][0], total_pages=4)

    def test_pages_json损坏时走降级而不是抛(self) -> None:
        job = _job(pages=2)
        storage = _seed_products(job, md_entries=_old_md_entries([(1, 2)]))
        storage.pages_json_path.write_text('[{"page_no": 1,', encoding="utf-8")

        payload = _confirmed_payload(job, [_item(1, 2, filename="降级.pdf")])

        assert payload["segments"][0]["content_md"].strip(), "降级路径也不能把正文丢成空串"
        _assert_segment_md(payload["segments"][0], total_pages=2)

    def test_没有任何旧产物时留空串而不是别人的正文(self) -> None:
        job = _job(pages=2)
        _seed_products(job, with_pages=False)

        payload = _confirmed_payload(job, [_item(1, 2, filename="什么都没有.pdf")])

        assert payload["segments"][0]["content_md"] == ""

    def test_页区间没变时页锚点原样保留(self) -> None:
        job = _job(pages=2)
        entries = _old_md_entries([(1, 2)])
        entries[0]["page_spans"] = [{"page": 1, "start": 0, "end": 6}, {"page": 2, "start": 6, "end": 12}]
        _seed_products(job, with_pages=False, md_entries=entries)

        payload = _confirmed_payload(job, [_item(1, 2, filename="锚点.pdf")])

        assert payload["segments"][0]["page_spans"] == entries[0]["page_spans"]
