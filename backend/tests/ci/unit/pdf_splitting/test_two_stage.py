"""两阶段任务链（取字 → 分段）的单元测试。

背景：Django-Q 的 worker 超时（DJANGO_Q_TIMEOUT，默认 600s）是**整个任务**的
阈值。164 页实测「取字 + 分段」合起来跑到 499s 就被杀（某次 164 页任务），而且
被杀后 OCR 成果全丢、只能从零重来。

拆分后：
- 取字阶段产物落 pages.json；
- 分段阶段从 pages.json 读回，有自己的 600s 预算；
- 分段被杀也不用重跑云端 OCR。

这里锁住落盘/读回/阶段推进的契约。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from apps.pdf_splitting.services.split import two_stage


def _storage(tmp_path: Path) -> Any:
    storage = MagicMock()
    storage.pages_json_path = tmp_path / "pages.json"

    def write_json(path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    storage.write_json.side_effect = write_json
    return storage


class TestSaveLoadPages:
    def test_roundtrip_dataclasses(self, tmp_path: Path) -> None:
        from dataclasses import dataclass

        @dataclass
        class _Page:
            page_no: int
            text: str

        storage = _storage(tmp_path)
        two_stage.save_pages(storage, [_Page(1, "甲"), _Page(2, "乙")])
        loaded = two_stage.load_pages(storage)

        assert loaded == [{"page_no": 1, "text": "甲"}, {"page_no": 2, "text": "乙"}]

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """pages.json 不存在时返回空表而不是抛异常——
        调用方据此判断「需重跑取字阶段」。"""
        storage = _storage(tmp_path)
        assert two_stage.load_pages(storage) == []

    def test_corrupt_json_returns_empty(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path)
        storage.pages_json_path.write_text("{ 不是合法 json", encoding="utf-8")
        assert two_stage.load_pages(storage) == []

    def test_non_list_payload_returns_empty(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path)
        storage.pages_json_path.write_text('{"a": 1}', encoding="utf-8")
        assert two_stage.load_pages(storage) == []


class TestAdvanceToSegmentStage:
    def test_submits_segment_task_and_updates_stage(self) -> None:
        """推进阶段时必须**重新提交一个独立任务**——这是拆链的核心：
        第二阶段的 600s 预算必须是全新的，不能被第一阶段耗掉。"""
        job = MagicMock()
        job.id = "job-1"
        job.progress = 50

        with (
            patch.object(two_stage, "submit_segment_stage", return_value="task-2") as submit,
            patch.object(two_stage.PdfSplitJob.objects, "filter") as flt,
        ):
            two_stage.advance_to_segment_stage(job, pages_count=164)

        submit.assert_called_once_with(job)
        kwargs = flt.return_value.update.call_args.kwargs
        assert kwargs["stage"] == "segment"
        assert kwargs["task_id"] == "task-2"
        assert "heartbeat_at" in kwargs


class TestMarkStageFailed:
    def test_records_which_stage_died(self) -> None:
        """失败必须写清阶段，否则排障时分不清是 OCR 挂了还是 LLM 挂了。"""
        with patch.object(two_stage.PdfSplitJob.objects, "filter") as flt:
            two_stage.mark_stage_failed("job-1", "extract", "mineru down")

        kwargs = flt.return_value.update.call_args.kwargs
        assert kwargs["status"] == "failed"
        assert kwargs["stage"] == "extract"
        assert "mineru down" in kwargs["error_message"]


class TestTaskNames:
    def test_task_paths_are_importable(self) -> None:
        """任务名写错会让 Django-Q 静默不执行——这里断言它们真实存在。"""
        import importlib

        for name in (two_stage.TASK_EXTRACT, two_stage.TASK_SEGMENT):
            module_path, func_name = name.rsplit(".", 1)
            module = importlib.import_module(module_path)
            assert callable(getattr(module, func_name)), f"{name} 不存在"


class TestStageTimeoutBudget:
    """每个阶段必须自带 timeout——不传就退回集群默认值，云端一抖就被硬杀。

    背景（2026-11-16，164 页全本双引擎）：
    · 双引擎实测 269s、分段 130s，看似离 600s 很远；
    · 但同一次事故里 MinerU 单路曾静默阻塞到 4347s（72 分钟）——
      云服务的长尾不是直觉能估的。
    所以预算按「实测 × 3」定额，并用 django-q 的单任务 timeout 覆盖集群默认值，
    而不是把全局值抬到能容忍最坏情况（那会让每个普通任务都享有巨大失控窗口）。
    """

    @staticmethod
    def _patched_submit():
        return patch("apps.pdf_splitting.services.split.two_stage.build_task_submission_service")

    def test_取字阶段带上自己的预算(self) -> None:
        job = MagicMock(id="job-1")
        with self._patched_submit() as factory:
            two_stage.submit_extract_stage(job)

        assert factory.return_value.submit.call_args.kwargs["timeout"] == two_stage.EXTRACT_STAGE_TIMEOUT_SECONDS

    def test_双引擎阶段预算最长(self) -> None:
        """双引擎要跑两遍整本，预算必须比另两段宽——否则它就失去单独拆出来的意义。"""
        job = MagicMock(id="job-1")
        with self._patched_submit() as factory:
            two_stage.submit_cross_check_stage(job)

        used = factory.return_value.submit.call_args.kwargs["timeout"]
        assert used == two_stage.CROSS_CHECK_STAGE_TIMEOUT_SECONDS
        assert used > two_stage.EXTRACT_STAGE_TIMEOUT_SECONDS
        assert used > two_stage.SEGMENT_STAGE_TIMEOUT_SECONDS

    def test_分段阶段带上自己的预算(self) -> None:
        job = MagicMock(id="job-1")
        with self._patched_submit() as factory:
            two_stage.submit_segment_stage(job)

        assert factory.return_value.submit.call_args.kwargs["timeout"] == two_stage.SEGMENT_STAGE_TIMEOUT_SECONDS

    def test_三个阶段的预算都远超集群默认值(self) -> None:
        """集群默认 600s 是全局小值兜底；阶段预算若比它还小就白加了。"""
        from apps.core.config.django_runtime import resolve_q_cluster

        cluster_default = int(resolve_q_cluster()["timeout"])
        for name in (
            "EXTRACT_STAGE_TIMEOUT_SECONDS",
            "CROSS_CHECK_STAGE_TIMEOUT_SECONDS",
            "SEGMENT_STAGE_TIMEOUT_SECONDS",
        ):
            assert getattr(two_stage, name) > cluster_default, f"{name} 不比集群默认值大，等于没设"
