"""「用户勾选多个引擎」这条链路：取值解析 → 任务字段归一化 → 取字阶段是否跑比对。

用户的原话是「不需要读配置呀，用户可以在自动分段的下拉菜单选择需要同时使用的
引擎即可」。所以这条链路上**没有任何 SystemConfig / 环境变量**，只有三件事：

· ``parse_dual_engines``：`'mineru,paddleocr_vl'` → `['mineru','paddleocr_vl']`；
· ``PdfSplitJobService._normalize_dual_engines``：去重后落库，空串 = 不跑比对；
· ``PdfSplitService.cross_check_stage``（原 `_run_dual_engine_if_selected`，现已拆为独立阶段任务）：**2 个及以上**才跑比对，
  空 / 1 个时整段跳过（单引擎路径一字未变，这是硬要求）。

`dual_engines` 与 `cloud_backend` 是两件事：前者是「另外再跑谁做比对」（纯附加），
后者是「取字用谁」（单选 + 容灾）。`paddleocr_vl` 不是可注册的解析平台
（`DocumentParseProvider.ProviderType` 里没有它），所以它只能出现在前者。

数据一律虚构。
"""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from apps.pdf_splitting.models import DUAL_ENGINE_CHOICES, parse_dual_engines
from apps.pdf_splitting.services.job_service import PdfSplitJobService
from apps.pdf_splitting.services.split import dual_engine_runner as runner
from apps.pdf_splitting.services.split import service as split_service


class _TmpPdf:
    """只提供 ``as_posix()`` 的假路径（接入点只用它写日志）。"""

    def as_posix(self) -> str:
        return "/tmp/x.pdf"


class TestParseDualEngines:
    def test_双引擎取值拆成两个(self) -> None:
        assert parse_dual_engines("mineru,paddleocr_vl") == ["mineru", "paddleocr_vl"]

    def test_空值表示不跑比对(self) -> None:
        for raw in ("", "  ", None):
            assert parse_dual_engines(raw) == [], raw

    def test_去空格大小写归一(self) -> None:
        assert parse_dual_engines(" MinerU , PaddleOCR_VL ") == ["mineru", "paddleocr_vl"]

    def test_保留勾选顺序不排序(self) -> None:
        # 顺序是语义：第一个是主引擎（cloud_backend 按它选）
        assert parse_dual_engines("textin,mineru") == ["textin", "mineru"]

    def test_去重(self) -> None:
        assert parse_dual_engines("mineru,mineru,paddleocr_vl") == ["mineru", "paddleocr_vl"]

    def test_非法值丢弃(self) -> None:
        # 纯新增字段，没有历史脏数据要兼容：认下未知值只会让下游多一条分支
        assert parse_dual_engines("mineru,bogus,auto") == ["mineru"]

    def test_合法值就是三个引擎码(self) -> None:
        assert set(DUAL_ENGINE_CHOICES) == {"mineru", "paddleocr_vl", "textin"}


class TestNormalizeDualEngines:
    def _normalize(self, raw: str | None) -> str:
        return PdfSplitJobService()._normalize_dual_engines(raw)

    def test_去重后拼回(self) -> None:
        assert self._normalize("paddleocr_vl, mineru ,mineru") == "paddleocr_vl,mineru"

    def test_空串保持不变(self) -> None:
        # 空串是正常值（不跑比对），不能被换成某个默认引擎
        for raw in ("", None, "  "):
            assert self._normalize(raw) == "", raw

    def test_能装进字段长度(self) -> None:
        # max_length=128；三个引擎码拼起来远小于它
        assert len(self._normalize("mineru,textin,paddleocr_vl")) <= 128


def _job(dual_engines: str) -> Any:
    """取字阶段只需要 job 上这几个字段（本测试不碰 DB）。"""
    return SimpleNamespace(id=uuid4(), dual_engines=dual_engines, template_key="filing_materials_v1")


class TestDualEngineGate:
    """``cross_check_stage`` 是唯一的接入点，门禁必须精确。"""

    @pytest.fixture(autouse=True)
    def _no_stage_writes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """把阶段/心跳写库换成空操作。

        本类的关注点是**门禁**（跑不跑、跑谁、分歧怎么记），刻意不碰 DB。但
        `cross_check_stage` 进入比对时会切 stage=cross_check 并起心跳
        线程——那两件事都是真写库的。这里替身掉，既保住「不碰 DB」的初衷，也
        不会在没开数据库访问的用例里炸掉。阶段切换本身由
        `test_heartbeat.TestCrossCheckStage` 用真库负责。
        """
        monkeypatch.setattr(split_service.PdfSplitService, "_enter_cross_check", lambda self, job: None)
        monkeypatch.setattr(split_service.PdfSplitService, "_exit_cross_check", lambda self, job: None)
        monkeypatch.setattr(split_service, "periodic_heartbeat", lambda job_id, interval=15: nullcontext())

    def _run(self, monkeypatch: pytest.MonkeyPatch, dual_engines: str) -> tuple[dict[str, Any], list[list[str]]]:
        calls: list[list[str]] = []

        def _fake_run(_pdf_path: Any, *, engine_factories: Any = None, **_kwargs: Any) -> Any:
            calls.append(list(engine_factories or {}))
            return SimpleNamespace(
                summary={
                    "engine_disagreements": [{"page_no": 1}],
                    "engine_disagree_summary": {"high": 1, "medium": 0, "low": 0},
                    "dual_engine": {"engines": {}, "pages": []},
                }
            )

        monkeypatch.setattr(split_service, "run_dual_engine", _fake_run)
        summary = split_service.PdfSplitService().cross_check_stage(_job(dual_engines), pdf_path=_TmpPdf())
        return summary, calls

    @pytest.mark.parametrize("dual_engines", ["", "  ", "mineru", "paddleocr_vl", "bogus"])
    def test_空或一引擎完全不跑比对(self, monkeypatch: pytest.MonkeyPatch, dual_engines: str) -> None:
        """硬要求：空 / 1 个引擎时**整段跳过**，summary 一个键都不加。

        单引擎路径（文本层 → 缓存 → 云端分批 → 本地 OCR → 容灾）不能有任何行为变化，
        连「多一个空的 engine_disagreements 键」都不行——那会让老任务与新任务的
        summary 形状不一致。
        """
        summary, calls = self._run(monkeypatch, dual_engines)

        assert summary == {}
        assert calls == []

    def test_老任务没有该字段时也不跑(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`getattr(job, "dual_engines", "")` 的兜底：字段缺失（老对象）→ 不跑比对。"""
        calls: list[Any] = []
        monkeypatch.setattr(split_service, "run_dual_engine", lambda *a, **k: calls.append(a))

        summary = split_service.PdfSplitService().cross_check_stage(SimpleNamespace(), pdf_path=_TmpPdf())

        assert summary == {}
        assert calls == []

    def test_两个引擎才跑比对并把分歧写进summary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        summary, calls = self._run(monkeypatch, "mineru,paddleocr_vl")

        assert calls == [[runner.ENGINE_MINERU, runner.ENGINE_PADDLEOCR_VL]]
        assert summary["engine_disagreements"] == [{"page_no": 1}]
        assert summary["engine_disagree_summary"] == {"high": 1, "medium": 0, "low": 0}
        # 本次真正跑的引擎与「勾了但没跑」的引擎都要能从 summary 看出来
        assert summary["dual_engine"]["selected"] == ["mineru", "paddleocr_vl"]
        assert summary["dual_engine"]["unavailable"] == []

    def test_勾了不支持的引擎时如实记下来(self, monkeypatch: pytest.MonkeyPatch) -> None:
        summary, calls = self._run(monkeypatch, "mineru,textin")

        # textin 的逐页结构还没接进 dual_engine：只跑 mineru，但必须说出来
        assert calls == [[runner.ENGINE_MINERU]]
        assert summary["dual_engine"]["unavailable"] == ["textin"]

    def test_比对失败不影响取字(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """分歧是附加信息：交叉校验炸了只记日志，取字本身已经成功。"""

        def _boom(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("云端炸了")

        monkeypatch.setattr(split_service, "run_dual_engine", _boom)
        summary = split_service.PdfSplitService().cross_check_stage(_job("mineru,paddleocr_vl"), pdf_path=_TmpPdf())

        assert summary == {}


class TestCloudBackendUntouched:
    """`cloud_backend` 必须保持原样：它受枚举约束，且 `paddleocr_vl` 不是解析平台。"""

    def test_cloud_backend选择集没有多值与paddleocr_vl(self) -> None:
        from apps.pdf_splitting.models import PdfSplitCloudBackend

        values = {choice for choice, _label in PdfSplitCloudBackend.choices}
        # deepseek 是合法的 cloud_backend（凭证在 SystemConfig，不走 DocumentParseProvider）；
        # paddleocr_vl 仍然不行——它没有独立于 cloud_backend 的第二条通道。
        assert values == {"auto", "mineru", "textin", "deepseek"}
        assert "paddleocr_vl" not in values
        assert all("," not in value for value in values)

    def test_cloud_backend字段仍是16长度单选(self) -> None:
        from apps.pdf_splitting.models import PdfSplitJob

        field = PdfSplitJob._meta.get_field("cloud_backend")
        assert field.max_length == 16

    def test_多值塞进cloud_backend仍落回auto(self) -> None:
        # 防回流：前端若把多值错传到 cloud_backend，行为必须回到「容灾」，不能半懂不懂
        assert PdfSplitJobService()._normalize_cloud_backend("mineru,paddleocr_vl") == "auto"


class TestLockedBackendUnavailableMessage:
    """锁定平台不可用时的失败文案：修复路径猜错，律师照着提示操作也没用。"""

    @staticmethod
    def _message(backend: str) -> str:
        from apps.pdf_splitting.services.split.pipeline import LockedCloudBackendUnavailable, PageTextExtractor

        stats: dict[str, Any] = {
            "cloud_candidates": [],
            "cloud_backend_requested": backend,
            "pending_page_numbers": [1],
        }
        with pytest.raises(LockedCloudBackendUnavailable) as excinfo:
            PageTextExtractor(ocr_handler=SimpleNamespace())._parse_cloud(Path("/tmp/fake.pdf"), stats)
        return str(excinfo.value)

    def test_deepseek锁定的修复路径是系统配置里的Key(self) -> None:
        # deepseek 的凭证不在「解析平台」管理页（没有 provider 行），提示必须指向 SystemConfig
        message = self._message("deepseek")
        assert "deepseek" in message
        assert "DEEPSEEK_OCR_API_KEY" in message
        assert "未降级" in message

    def test_mineru锁定的修复路径是解析平台管理页(self) -> None:
        message = self._message("mineru")
        assert "mineru" in message
        assert "「解析平台」管理页" in message
        assert "未降级" in message
