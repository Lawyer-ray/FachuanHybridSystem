"""校准骨架：`没测到` 必须是 None 而不是 0；Stage 门禁必须挡得住边界与 NaN。

两组用例比覆盖率更要紧，因为它们挡的正是"最像绿的红"：

1. 空输入若返回 0，报告上写着「一致率 0」——读的人分不清「判定完全不一致」与
   「根本没有数据」，而 0 还会作为真实低分进入 Stage 门禁。
2. `kappa` 恰好落在门槛上时按**达标**处理（"至少"含端点）；而 NaN 在任何比较下
   都是 False，若门禁只写正向条件，NaN 会一路滑到 Stage 1 而没人发现。

另有一组机器证据（`TestNoDjangoDependency`）：本包必须在**没有 Django** 的进程里跑得
起来，靠 subprocess 剥掉 `DJANGO_SETTINGS_MODULE` 实测，不靠人工检查 import 列表。
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from apps.agent.calibration.__main__ import main
from apps.agent.calibration.metrics import (
    DEFECT_CLASSES,
    CalibrationDataError,
    CalibrationMetrics,
    CalibrationPayload,
    CalibrationSample,
    JudgmentUnit,
    cohen_kappa,
    compute_metrics,
    load_payload,
    pabak,
    parse_payload,
)
from apps.agent.calibration.report import render_report
from apps.agent.calibration.stage import KAPPA_FLOOR, MIN_FAMILIES, RECALL_FLOOR, TIE_BAND, StageDecision, decide_stage

#: 仓库的 backend 根目录（`python -m apps.agent.calibration` 要以它为 cwd）。
_BACKEND_ROOT = Path(__file__).resolve().parents[5]


def _unit(
    lawyer_defect: bool,
    judge_defect_forward: bool,
    judge_defect_reverse: bool,
    *,
    defect_class: str = "miss",
    rubric_id: str = "rubric_a",
) -> JudgmentUnit:
    return JudgmentUnit(
        rubric_id=rubric_id,
        defect_class=defect_class,
        lawyer_defect=lawyer_defect,
        judge_defect_forward=judge_defect_forward,
        judge_defect_reverse=judge_defect_reverse,
    )


def _payload(*units: JudgmentUnit, samples: tuple[CalibrationSample, ...] | None = None) -> CalibrationPayload:
    return CalibrationPayload(
        rubric_id="contract_answer_v1",
        rubric_version="test",
        families_agreeing=MIN_FAMILIES,
        margin=0.2,
        samples=samples if samples is not None else (CalibrationSample(contract_id="C-1", items=units),),
    )


def _raw_item(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "rubric_id": "rubric_a",
        "defect_class": "miss",
        "lawyer_defect": True,
        "judge_defect_forward": True,
        "judge_defect_reverse": True,
    }
    item.update(overrides)
    return item


def _raw_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "rubric_id": "contract_answer_v1",
        "rubric_version": "test",
        "families_agreeing": 2,
        "margin": 0.2,
        "samples": [{"contract_id": "C-1", "items": [_raw_item()]}],
    }
    payload.update(overrides)
    return payload


class TestMetricsOnMissingData:
    def test_empty_samples_return_none_for_every_ratio(self) -> None:
        metrics = compute_metrics(_payload(samples=()))

        assert metrics.contracts == 0
        assert metrics.units == 0
        assert metrics.raw_agreement is None
        assert metrics.kappa is None
        assert metrics.pabak is None
        assert metrics.position_consistency is None
        assert [stat.recall for stat in metrics.subclass_recalls] == [None] * len(DEFECT_CLASSES)

    def test_sample_without_items_is_not_a_zero_score(self) -> None:
        metrics = compute_metrics(_payload())

        assert metrics.contracts == 1
        assert metrics.units == 0
        assert metrics.scored_units == 0
        assert metrics.raw_agreement is None

    def test_pabak_of_nan_is_none(self) -> None:
        assert pabak(math.nan) is None
        assert pabak(None) is None
        assert pabak(0.0) == pytest.approx(-1.0)

    def test_kappa_is_none_when_both_sides_stay_constant(self) -> None:
        # 双方都判"无缺陷"：po = 1，pe = 1，kappa 的分母 1 - pe 退化为 0（数学上无定义）。
        pairs = [(False, False)] * 4

        assert cohen_kappa(pairs) is None
        metrics = compute_metrics(_payload(*[_unit(False, False, False) for _ in range(4)]))
        assert metrics.raw_agreement == pytest.approx(1.0)
        assert metrics.kappa is None

    def test_tied_units_leave_the_agreement_denominator(self) -> None:
        metrics = compute_metrics(_payload(_unit(True, True, False), _unit(False, False, True)))

        assert metrics.units == 2
        assert metrics.tied_units == 2
        assert metrics.scored_units == 0
        assert metrics.raw_agreement is None
        assert metrics.position_consistency == pytest.approx(0.0)


class TestMetricsValues:
    def test_agreement_kappa_and_pabak_on_known_confusion(self) -> None:
        # 六条配对：四条一致、两条互相错位 → po = 4/6，pe = 0.5，kappa = PABAK = 1/3。
        units = [
            _unit(True, True, True),
            _unit(True, True, True),
            _unit(False, False, False),
            _unit(False, False, False),
            _unit(True, False, False),
            _unit(False, True, True),
        ]

        metrics = compute_metrics(_payload(*units))

        assert metrics.raw_agreement == pytest.approx(4 / 6)
        assert metrics.kappa == pytest.approx(1 / 3)
        assert metrics.pabak == pytest.approx(1 / 3)
        assert metrics.lawyer_defect_units == 3
        assert metrics.judge_defect_units == 3

    def test_subclass_recall_is_none_when_the_subclass_has_no_label(self) -> None:
        units = [
            _unit(True, True, True, defect_class="miss", rubric_id="miss_a"),
            _unit(False, False, False, defect_class="miss", rubric_id="miss_b"),
            _unit(True, False, False, defect_class="cite", rubric_id="cite_a"),
        ]

        metrics = compute_metrics(_payload(*units))

        assert metrics.recall_for("miss") == pytest.approx(1.0)
        assert metrics.recall_for("cite") == pytest.approx(0.0)
        assert metrics.recall_for("over") is None
        with pytest.raises(KeyError):
            metrics.recall_for("no-such-class")

    def test_position_consistency_keeps_tied_units_in_denominator(self) -> None:
        metrics = compute_metrics(
            _payload(_unit(True, True, True), _unit(True, False, False), _unit(True, True, False))
        )

        assert metrics.position_consistency == pytest.approx(2 / 3)


class TestPayloadValidation:
    def test_missing_file_raises_data_error(self, tmp_path) -> None:
        with pytest.raises(CalibrationDataError, match="找不到校准数据文件"):
            load_payload(tmp_path / "absent.json")

    def test_nan_margin_is_rejected(self) -> None:
        with pytest.raises(CalibrationDataError, match="有限数"):
            parse_payload(_raw_payload(margin=math.nan))

    def test_unknown_defect_class_is_rejected(self) -> None:
        with pytest.raises(CalibrationDataError, match="defect_class"):
            parse_payload(_raw_payload(samples=[{"contract_id": "C-1", "items": [_raw_item(defect_class="typo")]}]))

    def test_duplicate_contract_id_is_rejected(self) -> None:
        duplicated = [
            {"contract_id": "C-1", "items": [_raw_item()]},
            {"contract_id": "C-1", "items": [_raw_item()]},
        ]

        with pytest.raises(CalibrationDataError, match="contract_id 重复"):
            parse_payload(_raw_payload(samples=duplicated))

    def test_well_formed_payload_round_trips(self) -> None:
        payload = parse_payload(_raw_payload())

        assert payload.families_agreeing == 2
        assert payload.samples[0].items[0].judge_defect_reverse is True


class TestDecideStage:
    def test_kappa_below_floor_is_stage_0(self) -> None:
        decision = decide_stage(0.5, 0.95, 0.95, 2, 0.2)

        assert decision.stage == 0
        kappa_check = decision.checks[0]
        assert kappa_check.criterion == "kappa"
        assert kappa_check.met is False
        assert kappa_check.gap == pytest.approx(KAPPA_FLOOR - 0.5)

    def test_kappa_at_floor_with_every_gate_met_is_stage_2(self) -> None:
        decision = decide_stage(KAPPA_FLOOR, RECALL_FLOOR, RECALL_FLOOR, MIN_FAMILIES, TIE_BAND + 0.01)

        assert decision.stage == 2
        assert decision.unmet == ()

    def test_kappa_just_below_floor_is_stage_0(self) -> None:
        assert decide_stage(0.7499, 0.95, 0.95, 2, 0.2).stage == 0

    def test_kappa_that_is_not_measurable_is_stage_0(self) -> None:
        assert decide_stage(math.nan, 0.95, 0.95, 2, 0.2).stage == 0
        assert decide_stage(None, 0.95, 0.95, 2, 0.2).stage == 0

    def test_single_family_falls_back_to_stage_1(self) -> None:
        decision = decide_stage(0.8, 0.95, 0.95, 1, 0.2)

        assert decision.stage == 1
        assert [check.criterion for check in decision.unmet] == ["families_agreeing"]

    def test_miss_recall_below_floor_falls_back_to_stage_1(self) -> None:
        decision = decide_stage(0.8, 0.89, 0.95, 2, 0.2)

        assert decision.stage == 1
        assert [check.criterion for check in decision.unmet] == ["miss_recall"]

    def test_margin_at_tie_band_is_not_stage_2(self) -> None:
        # 平局带要"严格越过"：正好落在带上仍是 tie，不许用浮点小数决出胜负。
        assert decide_stage(0.8, 0.95, 0.95, 2, TIE_BAND).stage == 1
        assert decide_stage(0.8, 0.95, 0.95, 2, TIE_BAND + 0.01).stage == 2

    def test_unmeasured_recall_counts_as_failed_gate(self) -> None:
        decision = decide_stage(0.8, None, 0.95, 2, 0.2)

        assert decision.stage == 1
        assert [check.criterion for check in decision.unmet] == ["miss_recall"]
        assert decision.unmet[0].met is None


def _decision_for(metrics: CalibrationMetrics) -> StageDecision:
    return decide_stage(
        metrics.kappa,
        metrics.recall_for("miss"),
        metrics.recall_for("cite"),
        MIN_FAMILIES,
        0.2,
    )


class TestReport:
    def test_report_contains_the_four_required_sections_in_order(self) -> None:
        metrics = compute_metrics(_payload(_unit(True, True, True), _unit(False, True, True)))
        report = render_report(
            provenance="单元测试样本",
            rubric_id="contract_answer_v1",
            rubric_version="test",
            metrics=metrics,
            decision=_decision_for(metrics),
        )

        headings = ["## 1. 样本量", "## 2. 指标表", "## 3. 达标判定", "## 4. 未达标差距"]
        positions = [report.index(heading) for heading in headings]
        assert positions == sorted(positions)
        assert "单元测试样本" in report

    def test_unmeasured_metric_renders_as_dash_not_zero(self) -> None:
        metrics = compute_metrics(_payload(samples=()))
        report = render_report(
            provenance="单元测试样本",
            rubric_id="contract_answer_v1",
            rubric_version="test",
            metrics=metrics,
            decision=_decision_for(metrics),
        )

        assert "| Cohen κ | — |" in report
        assert "| Cohen κ | 0.000 |" not in report
        assert "无法度量" in report


class TestNoDjangoDependency:
    def test_dry_run_succeeds_without_django_settings(self) -> None:
        # 剥掉 DJANGO_SETTINGS_MODULE / PYTHONPATH：只要包内（含父包 apps/apps.agent）
        # 碰了 Django，这个子进程就会 AppRegistryNotReady / ImproperlyConfigured。
        env = {key: value for key, value in os.environ.items() if key not in {"DJANGO_SETTINGS_MODULE", "PYTHONPATH"}}

        completed = subprocess.run(
            [sys.executable, "-m", "apps.agent.calibration", "--dry-run"],
            cwd=_BACKEND_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

        assert completed.returncode == 0, completed.stderr
        assert "## 1. 样本量" in completed.stdout
        assert "内置合成样本" in completed.stdout


class TestCommandLine:
    def test_dry_run_prints_report_and_exits_zero(self, capsys) -> None:
        exit_code = main(["--dry-run"])
        captured = capsys.readouterr()

        assert exit_code == 0
        assert "## 1. 样本量" in captured.out
        assert "数据来源：内置合成样本" in captured.out
        assert "## 4. 未达标差距" in captured.out
        assert captured.err == ""

    def test_missing_data_file_exits_with_error_and_no_report(self, tmp_path, capsys) -> None:
        exit_code = main(["--data", str(tmp_path / "absent.json")])
        captured = capsys.readouterr()

        assert exit_code == 2
        assert "找不到校准数据文件" in captured.err
        assert captured.out == ""
