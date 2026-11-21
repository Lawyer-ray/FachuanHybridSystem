"""转正页回填（``rotated_backfill``）的单测。

背景（这些用例存在的理由）：双引擎的 PaddleOCR-VL 结果以前只用于比对，一个字也不进正文。
job ``523fabce`` 的 p52 因此至今是乱码——内容躺倒 90°、``/Rotate=0``，MinerU 报成功但
文本全错，VL 那一侧（开方向分类）自报 ``angle=270`` 且认对了 689 字。

本模块锁住四件事：

1. **规则**（用例 ①②③④⑤）：angle=270 的页被替换、angle=0 的页逐位不变、VL 文本为空
   绝不覆盖、无块时只换正文（layout 连引用都不换）、开关关掉完全不动；
2. **只有一个入口**（用例 ⑥）：``apply_rotated_backfill`` 在全仓只有一处调用点；
3. **summary 记账**（用例 ⑦）：每个跳过都带 reason；
4. **接线**（``TestCrossCheckWiring``）：``cross_check_stage`` 真的把 pages.json 改了、
   留了备份与报告、重跑幂等、VL 整体失败时一个字节都不动。

数据一律虚构（示例机构 / 张三丰 / 明显假号），不连网、不跑真引擎。
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitSourceType, PdfSplitStage
from apps.pdf_splitting.services.split import rotated_backfill as rb
from apps.pdf_splitting.services.split.dual_engine import ENGINE_MINERU, ENGINE_PADDLEOCR_VL, EngineBlock
from apps.pdf_splitting.services.split.dual_engine_runner import DualEngineOutcome
from apps.pdf_splitting.services.split.pipeline import build_page_descriptor
from apps.pdf_splitting.services.split.split_models import PageDescriptor

#: 乱码页的「主引擎正文」：用它当哨兵，任何「没换掉」的路径都会把它留在正文里。
GARBLED = "í¶•Ê∂ãÂ≠ó pp 1234"


def _page(
    page_no: int, text: str, *, layout: dict[str, Any] | None = None, source_method: str = "mineru_ocr"
) -> PageDescriptor:
    """造一个和取字阶段同形的 ``PageDescriptor``（派生字段都走真实推导）。"""
    return build_page_descriptor(
        page_no=page_no,
        text=text,
        source_method=source_method,
        ocr_failed=False,
        template_key="filing_materials_v1",
        layout=layout,
    )


def _mineru_layout(*texts: str) -> dict[str, Any]:
    """主引擎侧的一页版面（千分比，与 MinerU 同口径）。"""
    return {
        "page_no": 1,
        "blocks": [
            {"type": "text", "text": text, "text_level": None, "bbox": [72.0, 60.0, 400.0, 90.0]} for text in texts
        ],
        "text": "\n".join(texts),
        "width": 1000,
        "height": 1000,
    }


def _vl_block(page_no: int, text: str) -> EngineBlock:
    """VL 侧的一个块（坐标已是原页帧的归一化矩形，见 ``normalize_paddleocr_vl_blocks``）。"""
    return EngineBlock(
        engine=ENGINE_PADDLEOCR_VL,
        page_no=page_no,
        text=text,
        rect={"x": 0.1, "y": 0.12, "w": 0.62, "h": 0.03},
        block_type="doc_title",
        approx=False,
    )


class TestRules:
    def test_rotated_page_replaces_text_and_layout(self) -> None:
        """① angle=270 + VL 有文本有块 → 该页 text/layout/source_method 全换，其它页逐字段相等。"""
        normal = _page(10, "第十页：借款合同编号 123", layout=_mineru_layout("第十页：借款合同编号 123"))
        rotated = _page(52, GARBLED, layout=_mineru_layout(GARBLED))
        pages = [normal, rotated]
        before = copy.deepcopy(pages)
        good_text = "第五十二页：借款合同（示例机构）"

        result = rb.apply_rotated_backfill(
            pages,
            angles={10: 0, 52: 270},
            vl_text={52: good_text},
            vl_blocks={52: [_vl_block(52, good_text)]},
            enabled=True,
        )

        assert result.applied == (52,)
        assert result.skipped == {}
        assert rotated.text == good_text
        assert rotated.source_method == rb.SOURCE_METHOD_VL_ROTATION
        assert rotated.layout is not None
        # 版面必须与正文同源：块文字来自 VL，坐标是原页帧的千分比
        assert [block["text"] for block in rotated.layout["blocks"]] == [good_text]
        assert rotated.layout["width"] == 1000
        assert rotated.layout["blocks"][0]["bbox"] == [100.0, 120.0, 720.0, 150.0]
        # 派生字段跟着新正文一起重算，不能留旧候选分
        assert rotated.normalized_text != before[1].normalized_text
        assert rotated.top_candidates is not before[1].top_candidates
        # 其它页逐字段相等（dataclass 比较）
        assert pages[0] == before[0]

    def test_angle_zero_page_is_untouched(self) -> None:
        """② angle=0（没有转正）→ 零改动：即便 VL 同一页有「更好」的文本也不许碰。"""
        page = _page(10, "第十页：正常横排正文", layout=_mineru_layout("第十页：正常横排正文"))
        pages = [page]
        before = copy.deepcopy(pages)

        result = rb.apply_rotated_backfill(
            pages,
            angles={10: 0},
            vl_text={10: "VL 这一页也认了一遍"},
            vl_blocks={10: [_vl_block(10, "VL 这一页也认了一遍")]},
            enabled=True,
        )

        assert result.applied == ()
        # 非候选页不记账：它们本来就该逐位不变，逐页记 skip 只会把 summary 撑成噪声
        assert result.skipped == {}
        assert pages == before

    def test_empty_vl_text_never_overwrites(self) -> None:
        """③ VL 该页文本为空/全空白 → 跳过并记 ``vl_empty``，正文一个字都不动。"""
        page = _page(52, GARBLED, layout=_mineru_layout(GARBLED))
        pages = [page]
        before = copy.deepcopy(pages)

        result = rb.apply_rotated_backfill(
            pages,
            angles={52: 180},
            vl_text={52: "   \n\t "},
            vl_blocks={52: [_vl_block(52, "  ")]},
            enabled=True,
        )

        assert result.applied == ()
        assert result.skipped == {52: rb.REASON_VL_EMPTY}
        assert pages == before

    def test_no_blocks_replaces_text_only(self) -> None:
        """④ angle≠0 但 VL 无块 → 只换 text，layout 仍是原来那个对象（同一引用）。"""
        original_layout = _mineru_layout(GARBLED)
        page = _page(52, GARBLED, layout=original_layout)
        pages = [page]

        result = rb.apply_rotated_backfill(
            pages,
            angles={52: 270},
            vl_text={52: "第五十二页：只有文字没有版面"},
            vl_blocks={},
            enabled=True,
        )

        assert result.applied == (52,)
        assert result.skipped == {52: rb.REASON_LAYOUT_KEPT}
        assert page.text == "第五十二页：只有文字没有版面"
        assert page.layout is original_layout
        assert page.source_method == rb.SOURCE_METHOD_VL_ROTATION

    def test_disabled_switch_changes_nothing(self) -> None:
        """⑤ 开关关 → 完全不动（回滚到改动前的唯一手段）。"""
        page = _page(52, GARBLED, layout=_mineru_layout(GARBLED))
        pages = [page]
        before = copy.deepcopy(pages)

        result = rb.apply_rotated_backfill(
            pages,
            angles={52: 270},
            vl_text={52: "第五十二页：借款合同"},
            vl_blocks={52: [_vl_block(52, "第五十二页：借款合同")]},
            enabled=False,
        )

        assert result.applied == ()
        assert result.skipped == {52: rb.REASON_DISABLED}
        assert pages == before

    def test_second_run_is_idempotent(self) -> None:
        """已回填的页重跑只记 ``already_backfilled``：不重复改，也不把 VL 文本再套一层。"""
        page = _page(52, GARBLED, layout=_mineru_layout(GARBLED))
        pages = [page]
        kwargs = {
            "angles": {52: 270},
            "vl_text": {52: "第五十二页：借款合同"},
            "vl_blocks": {52: [_vl_block(52, "第五十二页：借款合同")]},
            "enabled": True,
        }
        assert rb.apply_rotated_backfill(pages, **kwargs).applied == (52,)
        after_first = copy.deepcopy(pages)

        second = rb.apply_rotated_backfill(pages, **kwargs)

        assert second.applied == ()
        assert second.skipped == {52: rb.REASON_ALREADY_BACKFILLED}
        assert pages == after_first

    def test_vl_total_failure_affects_no_page(self) -> None:
        """VL 整体失败（如本 job 的 HTTP 500）→ 三张表全空 → 一个候选页都没有。"""
        page = _page(52, GARBLED, layout=_mineru_layout(GARBLED))
        pages = [page]
        before = copy.deepcopy(pages)
        failed_outcome = DualEngineOutcome(
            engine_pages={ENGINE_MINERU: {52: GARBLED}, ENGINE_PADDLEOCR_VL: {}},
            blocks_by_engine={ENGINE_MINERU: [], ENGINE_PADDLEOCR_VL: []},
            disagreements=[],
            summary={"dual_engine": {"engines": {ENGINE_PADDLEOCR_VL: {"ok": False, "error": "HTTP 500"}}}},
        )
        view = rb.vl_page_view(failed_outcome)

        result = rb.apply_rotated_backfill(
            pages, angles=view.angles, vl_text=view.text, vl_blocks=view.blocks, enabled=True
        )

        assert (view.angles, view.text, view.blocks) == ({}, {}, {})
        assert result.applied == ()
        assert pages == before


class TestSummaryBlock:
    def test_counts_every_skip_reason(self) -> None:
        """⑦ applied / skipped 的数量与原因必须与判决一一对应。"""
        pages = [
            _page(10, "第十页正文"),
            _page(20, "第二十页正文", layout=_mineru_layout("第二十页正文")),
            _page(30, "第三十页正文", layout=_mineru_layout("第三十页正文")),
            _page(40, "第四十页正文", layout=_mineru_layout("第四十页正文")),
            _page(50, "第五十页正文", layout=_mineru_layout("第五十页正文")),
        ]
        pages[4].source_method = rb.SOURCE_METHOD_VL_ROTATION
        result = rb.apply_rotated_backfill(
            pages,
            angles={10: 0, 20: 90, 30: 180, 40: 270, 50: 270},
            vl_text={20: "第二十页：VL 正文", 30: "   ", 40: "第四十页：VL 正文", 50: "第五十页：VL 正文"},
            vl_blocks={20: [_vl_block(20, "第二十页：VL 正文")]},
            enabled=True,
        )

        block = rb.summary_block(result, enabled=True)

        assert result.applied == (20, 40)
        assert result.skipped == {30: rb.REASON_VL_EMPTY, 40: rb.REASON_LAYOUT_KEPT, 50: rb.REASON_ALREADY_BACKFILLED}
        assert block["enabled"] is True
        assert block["pages_applied"] == [20, 40]
        # 页号键在 JSON 里必然是字符串，这里就按字符串断言
        assert block["skipped"] == {"30": "vl_empty", "40": "layout_kept", "50": "already_backfilled"}
        assert block["skipped_counts"] == {"vl_empty": 1, "layout_kept": 1, "already_backfilled": 1}
        assert "error" not in block

    def test_disabled_block_says_so(self) -> None:
        """开关关着时 summary 必须能看出来（否则「为什么没回填」只能靠猜）。"""
        pages = [_page(52, GARBLED, layout=_mineru_layout(GARBLED))]
        result = rb.apply_rotated_backfill(
            pages, angles={52: 270}, vl_text={52: "第五十二页"}, vl_blocks={}, enabled=False
        )
        block = rb.summary_block(result, enabled=False)
        assert block["enabled"] is False
        assert block["skipped_counts"] == {"disabled": 1}


def test_backfill_block_reaches_job_summary_shape() -> None:
    """回填记账必须能进 job summary（cross_check 落盘 → 分段阶段拼装的两个环节都要带）。"""
    from apps.pdf_splitting.services.split.service import _dual_engine_summary

    block = {
        "enabled": True,
        "pages_applied": [52],
        "skipped": {"73": "vl_empty"},
        "skipped_counts": {"vl_empty": 1},
    }

    assert _dual_engine_summary({"rotated_backfill": block})["rotated_backfill"] == block
    # 没开双引擎 / 旧任务没有这份产物时形状也得在（前端不用写分支）
    assert _dual_engine_summary({})["rotated_backfill"] == {}


def _single_call_site() -> list[str]:
    """扫 ``backend/apps`` 找 ``apply_rotated_backfill`` 的**调用点**（AST，不看注释/字符串）。"""
    apps_root = Path(__file__).resolve().parents[4] / "apps"
    sites: list[str] = []
    for path in apps_root.rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - 读不到就当没写这个名字
            continue
        if "apply_rotated_backfill" not in source:
            continue
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name == "apply_rotated_backfill":
                sites.append(path.relative_to(apps_root.parent).as_posix())
                break
    return sites


class TestSingleEntry:
    def test_only_one_call_site_in_production_code(self) -> None:
        """⑥ 回填只有一个入口、一处调用点。

        为什么必须只有一个：判据（哪些页该换、空文本不覆盖、有块才换版面）只要出现
        第二份拷贝，两份就一定会漂移，而漂移的表现是「同一份卷宗在不同入口下正文
        不一样」——这种不一致没有任何报错，只能靠人肉比对才发现。

        调用点只有 ``service.cross_check_stage`` 的原因是**物理**的：那是全仓唯一
        同时拿得到 ``pages``（extract 阶段落的 pages.json）与 ``DualEngineOutcome``
        的地方（双引擎已拆成独立阶段，取字阶段手里没有 VL 结果）。将来若某个入口
        也需要回填，请在那里**调用同一个函数**并把这条断言改成两处，而不是复制判据。
        """
        assert _single_call_site() == ["apps/pdf_splitting/services/split/service.py"]


@pytest.fixture
def _isolated_media_root(tmp_path: Path, settings: Any) -> Path:
    """隔离 MEDIA_ROOT：pages.json / 备份 / 报告都写在任务目录下，绝不碰真实 media。"""
    settings.MEDIA_ROOT = tmp_path / "media"
    return tmp_path


def _make_job() -> PdfSplitJob:
    return PdfSplitJob.objects.create(
        id=uuid4(),
        source_type=PdfSplitSourceType.UPLOAD,
        source_original_name="示例卷宗.pdf",
        status=PdfSplitJobStatus.PROCESSING,
        stage=PdfSplitStage.CROSS_CHECK,
        progress=100,
        total_pages=3,
        processed_pages=3,
        current_page=3,
        dual_engines="mineru,paddleocr_vl",
        template_key="filing_materials_v1",
    )


def _outcome(
    *, vl_text: dict[int, str], vl_angles: dict[int, int], vl_blocks: dict[int, list[EngineBlock]]
) -> DualEngineOutcome:
    return DualEngineOutcome(
        engine_pages={ENGINE_MINERU: dict.fromkeys(vl_text, GARBLED), ENGINE_PADDLEOCR_VL: dict(vl_text)},
        blocks_by_engine={
            ENGINE_MINERU: [],
            ENGINE_PADDLEOCR_VL: [block for blocks in vl_blocks.values() for block in blocks],
        },
        disagreements=[],
        summary={"engine_disagreements": [], "engine_disagree_summary": {}, "dual_engine": {}},
        engine_page_angles={ENGINE_PADDLEOCR_VL: dict(vl_angles)},
    )


# transaction=True：`cross_check_stage` 里的心跳线程用另一条连接写库，包在用例事务里
# 会让它看不见这行（与 test_heartbeat.py 同一条理由）。
@pytest.mark.django_db(transaction=True)
class TestCrossCheckWiring:
    """接线：``cross_check_stage`` 把回填真正落到 pages.json + 报告 + summary。"""

    def _run(self, job: PdfSplitJob, outcome: DualEngineOutcome | None) -> dict[str, Any]:
        from apps.pdf_splitting.services.split.service import PdfSplitService

        with (
            patch("apps.pdf_splitting.services.split.service.run_dual_engine", return_value=outcome),
            patch("apps.pdf_splitting.services.split.service.plan_dual_engine_factories", return_value=({}, [])),
        ):
            return PdfSplitService().cross_check_stage(job, pdf_path=Path("/tmp/fake.pdf"))

    def _seed_pages(self, job: PdfSplitJob) -> tuple[Any, list[dict[str, Any]]]:
        from apps.pdf_splitting.services.split import two_stage
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        storage = PdfSplitStorage(job.id)
        storage.ensure_dirs()
        pages = [
            _page(1, "第一页：目录"),
            _page(2, GARBLED, layout=_mineru_layout(GARBLED)),
            _page(3, "第三页：落款"),
        ]
        two_stage.save_pages(storage, pages)
        raw = json.loads(storage.pages_json_path.read_text(encoding="utf-8"))
        # 未来版本才有的键：回写必须原样保留（不许「读成 dataclass 再整份序列化」）
        raw[1]["future_field"] = {"kept": True}
        storage.write_json(storage.pages_json_path, raw)
        return storage, raw

    def test_backfill_rewrites_pages_json_and_leaves_evidence(self, _isolated_media_root: Path) -> None:
        job = _make_job()
        storage, raw_before = self._seed_pages(job)
        good_text = "第二页：借款合同（示例机构）"
        outcome = _outcome(
            vl_text={2: good_text},
            vl_angles={1: 0, 2: 270, 3: 0},
            vl_blocks={2: [_vl_block(2, good_text)]},
        )

        summary = self._run(job, outcome)

        block = summary["rotated_backfill"]
        assert block["enabled"] is True
        assert block["pages_applied"] == [2]
        assert block["skipped"] == {}
        assert block["skipped_counts"] == {}

        raw_after = json.loads(storage.pages_json_path.read_text(encoding="utf-8"))
        assert raw_after[1]["text"] == good_text
        assert raw_after[1]["source_method"] == rb.SOURCE_METHOD_VL_ROTATION
        assert [item["text"] for item in raw_after[1]["layout"]["blocks"]] == [good_text]
        assert raw_after[1]["future_field"] == {"kept": True}
        # angle=0 的两页逐字段一字不变
        assert raw_after[0] == raw_before[0]
        assert raw_after[2] == raw_before[2]

        # 留痕：旧文件备份 + 报告（哪几页被换过、字数怎么变的唯一凭据）
        backups = sorted(storage.analysis_dir.glob("pages.json.bak-*"))
        assert len(backups) == 1
        assert json.loads(backups[0].read_text(encoding="utf-8"))[1]["text"] == GARBLED
        report = json.loads(storage.rotated_backfill_json_path.read_text(encoding="utf-8"))
        assert report["enabled"] is True
        assert report["written_at"]
        assert report["applied"] == [
            {
                "page": 2,
                "angle": 270,
                "text_chars_before": len(GARBLED),
                "text_chars_after": len(good_text),
                "layout_replaced": True,
            }
        ]
        assert report["skipped"] == {}

    def test_rerun_is_idempotent_and_keeps_previous_result(self, _isolated_media_root: Path) -> None:
        """第二次跑只记 ``already_backfilled``；VL 这次失败也不回滚上一次的正文。"""
        job = _make_job()
        storage, _ = self._seed_pages(job)
        good_text = "第二页：借款合同（示例机构）"
        outcome = _outcome(vl_text={2: good_text}, vl_angles={2: 270}, vl_blocks={2: [_vl_block(2, good_text)]})
        self._run(job, outcome)

        # 第二次：VL 整体失败（HTTP 500 那种），三张表全空
        failed = DualEngineOutcome(
            engine_pages={ENGINE_MINERU: {2: GARBLED}, ENGINE_PADDLEOCR_VL: {}},
            blocks_by_engine={},
            disagreements=[],
            summary={"dual_engine": {}},
        )
        second = self._run(job, failed)

        assert second["rotated_backfill"]["pages_applied"] == []
        raw_after = json.loads(storage.pages_json_path.read_text(encoding="utf-8"))
        assert raw_after[1]["text"] == good_text

        # 第三次：VL 又恢复，但该页已回填 → already_backfilled，不再改一次
        third = self._run(job, outcome)
        assert third["rotated_backfill"]["pages_applied"] == []
        assert third["rotated_backfill"]["skipped"] == {"2": rb.REASON_ALREADY_BACKFILLED}
        assert json.loads(storage.pages_json_path.read_text(encoding="utf-8"))[1]["text"] == good_text

    def test_vl_total_failure_leaves_pages_json_untouched(self, _isolated_media_root: Path) -> None:
        """红线：VL 失败（如本 job 的 HTTP 500）时 pages.json 一个字节都不变、不写备份。"""
        job = _make_job()
        storage, _ = self._seed_pages(job)
        before = storage.pages_json_path.read_bytes()
        failed = DualEngineOutcome(
            engine_pages={ENGINE_MINERU: {2: GARBLED}, ENGINE_PADDLEOCR_VL: {}},
            blocks_by_engine={},
            disagreements=[],
            summary={"dual_engine": {"engines": {ENGINE_PADDLEOCR_VL: {"ok": False, "error": "HTTP 500"}}}},
        )

        summary = self._run(job, failed)

        assert summary["rotated_backfill"]["pages_applied"] == []
        assert storage.pages_json_path.read_bytes() == before
        assert not list(storage.analysis_dir.glob("pages.json.bak-*"))


def test_dual_engine_runner_exposes_per_page_angles(tmp_path: Path) -> None:
    """角度透出：``_run_paddleocr_vl`` 顺带读 ``doc_preprocessor_res.angle``（脏值→0）。"""
    import pymupdf as fitz

    from apps.pdf_splitting.services.split import dual_engine_runner as runner

    pdf = tmp_path / "sample.pdf"
    doc = fitz.open()
    try:
        for index in range(2):
            doc.new_page(width=595, height=842).insert_text((72, 72), f"page {index + 1}")
        pdf.write_bytes(doc.tobytes())
    finally:
        doc.close()

    def _no_mineru() -> Any:
        """MinerU 本用例不跑（它没有方向分类）：工厂直接炸，编排层必须只坏它自己。"""
        raise RuntimeError("本用例只关心 VL 的角度透出")

    class _VL:
        def recognize_bytes(self, payload: bytes, **_kwargs: Any) -> Any:
            return type(
                "Result",
                (),
                {
                    "text": "merged",
                    "layout_results": [
                        # 第 1 页转正过 270°；第 2 页是脏值（→0，绝不当成 270 去回填）
                        {"markdown": {"text": "第一页"}, "prunedResult": {"doc_preprocessor_res": {"angle": 270}}},
                        {"markdown": {"text": "第二页"}, "prunedResult": {"doc_preprocessor_res": {"angle": "怪值"}}},
                    ],
                },
            )()

    outcome = runner.run_dual_engine(
        pdf,
        engine_factories={ENGINE_MINERU: _no_mineru, ENGINE_PADDLEOCR_VL: _VL},
    )

    assert outcome.engine_page_angles[ENGINE_PADDLEOCR_VL] == {1: 270, 2: 0}
    # MinerU 没跑起来（工厂直接炸，由 run_dual_engine 兜住），角度表也必须是空 dict
    assert outcome.engine_page_angles[ENGINE_MINERU] == {}
    assert outcome.summary["dual_engine"]["engines"][ENGINE_MINERU]["ok"] is False
