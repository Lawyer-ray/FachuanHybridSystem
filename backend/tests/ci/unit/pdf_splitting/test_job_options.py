"""任务级选项：分歧自动裁定开关（``ocr_judge_enabled``）与分段策略（``segment_strategy``）。

## 为什么这两个要单独测

它们原本只活在**部署级** SystemConfig 里（``OCR_JUDGE_ENABLED`` /
``PDF_SPLIT_SEGMENT_STRATEGY``），律师想「这一份卷宗不自动裁定」「这一份要看全本」
只能去改系统配置——改完影响所有人，还得改回来。现在它们是**每个任务上的输入**，
全局配置降级成「部署默认值 / 能力总闸」。

这一改动有三处最容易错，也正是本文件的断言对象：

1. **默认值**：判定默认**开**（关掉会让绝大多数用户永远用不到这个能力），
   分段策略默认 ``batch``（整本一次在大卷宗上会撞 LLM 超时）。
2. **非法值必须报错**：静默回落会让用户以为「整本一次」真的跑了 / 判定坏了。
3. **``enabled`` 与 ``requested`` 是两个值**：前者是**有效值**（任务要求 ∧ 部署可用），
   后者是用户要求值。只回显全局开关时，前端分不清「用户没要」和「用户要了但缺 key」。

数据一律虚构（张三丰 / 张三半 / 示例卷宗）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pymupdf as fitz
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.exceptions import ValidationException
from apps.core.services.system_config_service import SystemConfigService
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitSegmentStrategy
from apps.pdf_splitting.services.job_service import PdfSplitJobService
from apps.pdf_splitting.services.split import disagreement_judge
from apps.pdf_splitting.services.split import dual_engine_runner as runner
from apps.pdf_splitting.services.split.pipeline import resolve_segment_strategy

pytestmark = pytest.mark.django_db

#: create_job 里的两个任务提交入口（缺一个就会真的往队列里塞任务）。
_SUBMIT_PATH = "apps.pdf_splitting.services.job_service.build_task_submission_service"
_STAGE_SUBMIT_PATH = "apps.pdf_splitting.services.split.two_stage.build_task_submission_service"


@contextmanager
def _patched_submits() -> Iterator[MagicMock]:
    factory = MagicMock()
    factory.return_value.submit.return_value = "task-stub"
    with patch(_SUBMIT_PATH, factory), patch(_STAGE_SUBMIT_PATH, factory):
        yield factory


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path: Path, settings: Any) -> Path:
    """``create_job`` 会真的写盘（源文件副本 + 任务目录），不能写进开发环境的 media。"""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def _make_pdf(path: Path, *, pages: int = 2) -> Path:
    """生成一份可被 pymupdf 打开的最小 PDF。"""
    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"page {index + 1}")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    doc.close()
    return path


def _upload(path: Path, *, name: str = "示例卷宗.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, path.read_bytes(), content_type="application/pdf")


def _create(pdf: Path, **options: Any) -> PdfSplitJob:
    with _patched_submits():
        return PdfSplitJobService().create_job(
            file=_upload(pdf),
            source_path=None,
            template_key="filing_materials_v1",
            **options,
        )


# ── 判定开关：落库默认值与字符串写法 ──────────────────────────────


class TestOcrJudgeEnabledOption:
    def test_不传时默认开启(self, tmp_path: Path) -> None:
        """用户明确要求「判定默认开启」：默认关等于让这个能力默认不存在。"""
        job = _create(_make_pdf(tmp_path / "默认.pdf"))
        job.refresh_from_db()

        assert job.ocr_judge_enabled is True

    def test_可以按任务关掉(self, tmp_path: Path) -> None:
        job = _create(_make_pdf(tmp_path / "关掉.pdf"), ocr_judge_enabled=False)
        job.refresh_from_db()

        assert job.ocr_judge_enabled is False

    def test_表单字符串关掉也落库为假(self, tmp_path: Path) -> None:
        job = _create(_make_pdf(tmp_path / "表单.pdf"), ocr_judge_enabled="off")
        job.refresh_from_db()

        assert job.ocr_judge_enabled is False

    @pytest.mark.parametrize("raw", ["1", "true", "TRUE", "Yes", "on", True])
    def test_真值写法(self, raw: str | bool) -> None:
        assert PdfSplitJobService()._normalize_ocr_judge_enabled(raw) is True

    @pytest.mark.parametrize("raw", ["0", "false", "False", "no", "OFF", False])
    def test_假值写法(self, raw: str | bool) -> None:
        assert PdfSplitJobService()._normalize_ocr_judge_enabled(raw) is False

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_空值按默认开处理(self, raw: str | None) -> None:
        assert PdfSplitJobService()._normalize_ocr_judge_enabled(raw) is True

    def test_非法值报校验错误而不是静默当假(self) -> None:
        """静默当 False 等于把一条分歧静默交给人工（或者没交）——必须让调用方知道。"""
        with pytest.raises(ValidationException) as exc_info:
            PdfSplitJobService()._normalize_ocr_judge_enabled("maybe")

        assert "ocr_judge_enabled" in exc_info.value.message
        assert "合法取值" in str(exc_info.value.errors["ocr_judge_enabled"])


# ── 分段策略：默认值、落库、非法值 ────────────────────────────


class TestSegmentStrategyOption:
    def test_默认分批摘要(self, tmp_path: Path) -> None:
        job = _create(_make_pdf(tmp_path / "默认策略.pdf"))
        job.refresh_from_db()

        assert job.segment_strategy == PdfSplitSegmentStrategy.BATCH

    def test_整本一次落库正确(self, tmp_path: Path) -> None:
        job = _create(_make_pdf(tmp_path / "整本.pdf"), segment_strategy="wholebook")
        job.refresh_from_db()

        assert job.segment_strategy == PdfSplitSegmentStrategy.WHOLEBOOK

    def test_三种合法值都在choices里(self) -> None:
        assert [choice for choice, _label in PdfSplitSegmentStrategy.choices] == [
            "batch",
            "wholebook",
            "wholebook_cross",
        ]

    def test_非法值报错且列出合法取值(self) -> None:
        with pytest.raises(ValidationException) as exc_info:
            PdfSplitJobService()._normalize_segment_strategy("fastest")

        errors = " ".join(str(value) for value in (exc_info.value.errors or {}).values())
        assert "segment_strategy" in exc_info.value.message
        assert "batch" in errors
        assert "wholebook" in errors
        assert "wholebook_cross" in errors

    def test_非法策略不留下半个任务(self, tmp_path: Path) -> None:
        """校验在落库之前：报错时既不该有任务行，也不该有任务目录。"""
        with pytest.raises(ValidationException):
            _create(_make_pdf(tmp_path / "非法.pdf"), segment_strategy="fastest")

        assert PdfSplitJob.objects.count() == 0


# ── 材料包归属：任务必须记得自己是哪个包提交的 ───────────────────
#
# 不落库的后果不是报错，而是**张冠李戴**：接管在飞任务 / 复用已算好的任务
# 只按「文件名 + 页数」匹配，两个包里各有一份「材料.pdf / 37 页」就互相串，
# 律师看到的是另一个包的进度条，或者更糟——另一个包的识别正文被当成本包的。


class TestPackMessageIdOption:
    def test_传了材料包主键就落库(self, tmp_path: Path) -> None:
        job = _create(_make_pdf(tmp_path / "带包.pdf"), pack_message_id=617)
        job.refresh_from_db()

        assert job.pack_message_id == 617

    def test_不传时为空(self, tmp_path: Path) -> None:
        """脚本 / 后台直提的任务没有所属包，必须允许为空（不能因此报错）。"""
        job = _create(_make_pdf(tmp_path / "无包.pdf"))
        job.refresh_from_db()

        assert job.pack_message_id is None


# ── 部署默认值：任务字段优先，SystemConfig 只作兜底 ──────────────────


def _stub_system_config(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    def _get_value(self: Any, key: str, default: str = "") -> str:
        return value if key == "PDF_SPLIT_SEGMENT_STRATEGY" else default

    monkeypatch.setattr(SystemConfigService, "get_value", _get_value)


class TestResolveSegmentStrategyPriority:
    def test_任务级选择原样透出(self) -> None:
        assert resolve_segment_strategy(PdfSplitSegmentStrategy.WHOLEBOOK) == "wholebook"

    def test_任务级选择压过部署配置(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """部署配了整本一次，任务显式选分批 → 必须按任务来（用户选择 > 部署默认）。"""
        _stub_system_config(monkeypatch, "wholebook")

        assert resolve_segment_strategy("batch") == "batch"

    def test_任务没选时读部署配置(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_system_config(monkeypatch, "wholebook_cross")

        assert resolve_segment_strategy(None) == "wholebook_cross"

    def test_都没有时落回分批(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_system_config(monkeypatch, "")

        assert resolve_segment_strategy("") == "batch"


# ── 判定的两级门禁：enabled（有效值）/ requested（用户要求值）──────────


def _two_engine_factories() -> dict[str, Any]:
    """两个引擎的工厂桩：本文件把「跑引擎」整体替换掉了，工厂只用来定键集。"""
    return {runner.ENGINE_MINERU: object, runner.ENGINE_PADDLEOCR_VL: object}


def _stub_engine_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    """造一处分歧（张三丰 / 张三半），不碰任何云端。

    必须真有分歧：否则「判定没跑」可能只是因为没东西可判，测不出门禁。
    """
    monkeypatch.setattr(
        runner,
        "_run_engines_parallel",
        lambda *args, **kwargs: {
            runner.ENGINE_MINERU: ({1: "借款人：张三丰"}, [], {}, ""),
            runner.ENGINE_PADDLEOCR_VL: ({1: "借款人：张三半"}, [], {}, ""),
        },
    )


class TestRunDualEngineJudgeGate:
    def test_任务关掉判定时一次都不跑(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pdf = _make_pdf(tmp_path / "判定关.pdf", pages=1)
        _stub_engine_texts(monkeypatch)
        judge_spy = MagicMock(return_value={})
        monkeypatch.setattr(runner, "judge_disagreements", judge_spy)

        outcome = runner.run_dual_engine(pdf, engine_factories=_two_engine_factories(), judge_enabled=False)

        judge_spy.assert_not_called()
        # 确实有分歧却没判 —— 证明不是「没东西可判」才没跑的
        assert outcome.disagreements
        assert outcome.summary[runner.SUMMARY_ENGINE_DISAGREE_JUDGE] == {
            "enabled": False,
            "requested": False,
            "reason": disagreement_judge.GATE_NOT_REQUESTED,
            "annotated": 0,
            "accepted": 0,
            "human": 0,
            "reasons": {},
        }

    def test_要求开但部署侧缺key时_enabled为假requested为真(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pdf = _make_pdf(tmp_path / "缺key.pdf", pages=1)
        _stub_engine_texts(monkeypatch)
        monkeypatch.setattr(runner, "gate_state", lambda: (False, disagreement_judge.GATE_MISSING_KEY))
        judge_spy = MagicMock(return_value={})
        monkeypatch.setattr(runner, "judge_disagreements", judge_spy)

        outcome = runner.run_dual_engine(pdf, engine_factories=_two_engine_factories(), judge_enabled=True)

        judge_spy.assert_not_called()
        judge = outcome.summary[runner.SUMMARY_ENGINE_DISAGREE_JUDGE]
        assert judge["enabled"] is False
        assert judge["requested"] is True
        assert judge["annotated"] == 0
        # 缺 key 与「总闸没开」是两个配置项：原因码必须能分开，否则界面只能说「未生效」
        assert judge["reason"] == disagreement_judge.GATE_MISSING_KEY

    def test_任务要开且部署侧可用时真跑一次(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pdf = _make_pdf(tmp_path / "可用.pdf", pages=1)
        _stub_engine_texts(monkeypatch)
        monkeypatch.setattr(runner, "gate_state", lambda: (True, disagreement_judge.GATE_ENABLED))
        judge_spy = MagicMock(return_value={})
        monkeypatch.setattr(runner, "judge_disagreements", judge_spy)

        outcome = runner.run_dual_engine(pdf, engine_factories=_two_engine_factories(), judge_enabled=True)

        assert judge_spy.call_count == 1
        judge = outcome.summary[runner.SUMMARY_ENGINE_DISAGREE_JUDGE]
        assert judge["enabled"] is True
        assert judge["requested"] is True
        assert judge["reason"] == disagreement_judge.GATE_ENABLED

    def test_未传开关时跟随部署侧(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """None = 调用方没表态：仍按部署侧决定，不能悄悄变成「不判」。"""
        pdf = _make_pdf(tmp_path / "未表态.pdf", pages=1)
        _stub_engine_texts(monkeypatch)
        monkeypatch.setattr(runner, "gate_state", lambda: (True, disagreement_judge.GATE_ENABLED))
        judge_spy = MagicMock(return_value={})
        monkeypatch.setattr(runner, "judge_disagreements", judge_spy)

        outcome = runner.run_dual_engine(pdf, engine_factories=_two_engine_factories())

        assert judge_spy.call_count == 1
        assert outcome.summary[runner.SUMMARY_ENGINE_DISAGREE_JUDGE]["requested"] is True
        assert outcome.summary[runner.SUMMARY_ENGINE_DISAGREE_JUDGE]["reason"] == disagreement_judge.GATE_ENABLED
