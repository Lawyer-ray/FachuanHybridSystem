"""把指标与门禁结论渲染成 markdown 报告骨架。

四条硬规矩：

1. **四节必填且顺序固定**：样本量 → 指标表 → 达标判定 → 未达标差距。缺任何一节，
   这份报告就没法被别人复核（"一共有几个样本"和"差多少"是最先被问的两句）。
2. **数字一律来自入参**。本文件里没有任何字面量数字：一旦模板里写了示例值，
   dry-run 出来的报告就会被当成真实结论截图引用。门槛值也只在 ``stage.py`` 里定义一次。
3. **"测不到"渲染成 ``—``，绝不渲染成 0**。0 是"测到了且完全不一致"，
   两者在评审会上是完全不同的结论。
4. **未达标必须写差距**（门槛 − 实测）。只写"未达标"，"差一点"和"差很远"
   在报告上看起来一样，下一波不知道从哪里补样本。
"""

from __future__ import annotations

from .metrics import CalibrationMetrics
from .stage import COUNT_UNIT, RATIO_UNIT, STAGE_LABELS, StageCheck, StageDecision

#: 判定项 → 报告里的中文名。键与 ``decide_stage`` 的参数名一一对应。
_CRITERION_LABELS: dict[str, str] = {
    "kappa": "Cohen κ",
    "miss_recall": "漏改 recall",
    "cite_recall": "引用失效 recall",
    "families_agreeing": "同向 judge 家族数",
    "margin": "margin（对平局带）",
}

#: 指标表的三列内容（键 → （显示名，算法口径））。口径是纯文字，不含数字。
_METRIC_ROWS: tuple[tuple[str, str, str], ...] = (
    ("raw_agreement", "raw 一致率", "两向一致的单元里 judge 与律师同判的比例"),
    ("kappa", "Cohen κ", "扣掉偶然一致后的 kappa"),
    ("pabak", "PABAK", "极偏分布下的对照口径"),
    ("position_consistency", "位置一致性", "换序两向同向的单元 / 全部单元"),
)

_UNMEASURED = "—"


def render_report(
    *,
    provenance: str,
    rubric_id: str,
    rubric_version: str,
    metrics: CalibrationMetrics,
    decision: StageDecision,
) -> str:
    """渲染完整报告。``provenance`` 写清数据来源（真实文件路径，或 dry-run 合成样本）。"""
    header = "\n".join(
        [
            "# 评审校准报告（骨架）",
            "",
            f"- 数据来源：{provenance}",
            f"- rubric：{rubric_id} / {rubric_version}",
        ]
    )
    blocks = [
        header,
        _samples_section(metrics),
        _metrics_section(metrics),
        _verdict_section(decision),
        _gap_section(decision),
    ]
    # 节与节之间必须空一行：markdown 里紧跟表格/列表的标题不会被渲染成标题。
    return "\n\n".join(block.strip("\n") for block in blocks) + "\n"


def _samples_section(metrics: CalibrationMetrics) -> str:
    return "\n".join(
        [
            "## 1. 样本量",
            "",
            f"- 合同数：{_fmt(metrics.contracts, COUNT_UNIT)}",
            f"- 判定单元（合同 × rubric）：{_fmt(metrics.units, COUNT_UNIT)}",
            f"- 换序两向不一致（记 tie，不进一致率/kappa 分母）：{_fmt(metrics.tied_units, COUNT_UNIT)}",
            f"- 计入一致率/kappa 的单元：{_fmt(metrics.scored_units, COUNT_UNIT)}",
            f"- 律师标「有缺陷」的单元：{_fmt(metrics.lawyer_defect_units, COUNT_UNIT)}",
            f"- judge 判「有缺陷」的单元：{_fmt(metrics.judge_defect_units, COUNT_UNIT)}",
            "",
        ]
    )


def _metrics_section(metrics: CalibrationMetrics) -> str:
    rows = [
        "## 2. 指标表",
        "",
        "| 指标 | 数值 | 口径 |",
        "|:--|--:|:--|",
    ]
    values: dict[str, float | None] = {
        "raw_agreement": metrics.raw_agreement,
        "kappa": metrics.kappa,
        "pabak": metrics.pabak,
        "position_consistency": metrics.position_consistency,
    }
    for key, label, note in _METRIC_ROWS:
        rows.append(f"| {label} | {_fmt(values[key], RATIO_UNIT)} | {note} |")
    for stat in metrics.subclass_recalls:
        support = f"律师标注 {_fmt(stat.gold_positives, COUNT_UNIT)} 条，命中 {_fmt(stat.hits, COUNT_UNIT)} 条"
        rows.append(f"| recall · {stat.label} | {_fmt(stat.recall, RATIO_UNIT)} | {support} |")
    rows.append("")
    return "\n".join(rows)


def _verdict_section(decision: StageDecision) -> str:
    rows = [
        "## 3. 达标判定",
        "",
        f"- 结论：{STAGE_LABELS.get(decision.stage, '未知档位')}",
        "",
        "| 判定项 | 实测 | 门槛 | 结论 |",
        "|:--|--:|--:|:--|",
    ]
    for check in decision.checks:
        rows.append(
            f"| {_criterion_label(check)} | {_fmt(check.actual, check.unit)} "
            f"| {check.rule} {_fmt(check.threshold, check.unit)} | {_met_text(check)} |"
        )
    rows.extend(
        [
            "",
            "> 本批骨架只覆盖上表这几项门禁；raw / 位置一致性 / 越界误纳率 / 单 rubric 分歧率 /"
            " 人-人一致率上限属于后续报告范围，未参与本次判定。",
            "",
        ]
    )
    return "\n".join(rows)


def _gap_section(decision: StageDecision) -> str:
    rows = ["## 4. 未达标差距", ""]
    if not decision.unmet:
        rows.extend([f"- 无：上表门禁全部达标（{STAGE_LABELS[2]}）。", ""])
        return "\n".join(rows)
    for check in decision.unmet:
        if check.actual is None:
            rows.append(
                f"- {_criterion_label(check)}：无法度量（门槛 {check.rule} "
                f"{_fmt(check.threshold, check.unit)}），按未达标处理"
            )
            continue
        rows.append(
            f"- {_criterion_label(check)}：实测 {_fmt(check.actual, check.unit)}，门槛 {check.rule} "
            f"{_fmt(check.threshold, check.unit)}，差 {_fmt(check.gap, check.unit)}"
        )
    rows.append("")
    return "\n".join(rows)


def _criterion_label(check: StageCheck) -> str:
    return _CRITERION_LABELS.get(check.criterion, check.criterion)


def _met_text(check: StageCheck) -> str:
    if check.met is None:
        return "无法度量"
    return "达标" if check.met else "未达标"


def _fmt(value: float | int | None, unit: str) -> str:
    """``None`` → ``—``；计数按整数显示；比例固定三位小数（``0`` 与 ``0.000`` 不是一回事）。"""
    if value is None:
        return _UNMEASURED
    if unit == COUNT_UNIT:
        return str(int(value))
    return f"{float(value):.3f}"
