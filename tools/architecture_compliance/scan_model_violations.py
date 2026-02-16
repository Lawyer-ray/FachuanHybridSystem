"""
Model层违规扫描与风险评估

扫描 backend/apps/ 下所有 Model 文件，识别 save() 覆写，
使用 SaveMethodAnalyzer 分析业务逻辑复杂度，按风险等级分类并输出报告。

风险等级定义：
- 低风险：只有简单字段赋值 + super().save()，无业务逻辑块
- 中风险：有 1-2 个业务逻辑块
- 高风险：有 3+ 个业务逻辑块或包含外部服务调用
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .logging_config import get_logger, setup_logging
from .model_scanner import ModelLayerScanner
from .models import ModelViolation, Violation
from .save_method_analyzer import BLOCK_BUSINESS_LOGIC, SaveMethodAnalysis, SaveMethodAnalyzer

logger = get_logger("scan_model_violations")

# ── 路径常量 ────────────────────────────────────────────────

_BACKEND_APPS_DIR: Path = Path("backend/apps")
_OUTPUT_DIR: Path = Path("tools/architecture_compliance/output")

# ── 风险等级常量 ────────────────────────────────────────────

RISK_LOW: str = "低风险"
RISK_MEDIUM: str = "中风险"
RISK_HIGH: str = "高风险"

# 外部服务调用关键词（出现即升级为高风险）
_EXTERNAL_SERVICE_KEYWORDS: frozenset[str] = frozenset(
    {
        "外部服务调用",
        "实例化服务",
    }
)


# ── 数据模型 ────────────────────────────────────────────────


@dataclass
class ModelRiskAssessment:
    """单个 Model 的风险评估结果"""

    model_name: str
    file_path: str
    risk_level: str
    business_logic_count: int
    business_logic_summary: list[str] = field(default_factory=list)
    has_external_service_call: bool = False
    total_blocks: int = 0
    extraction_recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """转换为字典"""
        return {
            "model_name": self.model_name,
            "file_path": self.file_path,
            "risk_level": self.risk_level,
            "business_logic_count": self.business_logic_count,
            "business_logic_summary": self.business_logic_summary,
            "has_external_service_call": self.has_external_service_call,
            "total_blocks": self.total_blocks,
            "extraction_recommendations": self.extraction_recommendations,
        }


@dataclass
class ModelViolationReport:
    """Model层违规扫描总报告"""

    total_models_with_save: int = 0
    total_violations: int = 0
    risk_counts: dict[str, int] = field(
        default_factory=lambda: {
            RISK_LOW: 0,
            RISK_MEDIUM: 0,
            RISK_HIGH: 0,
        }
    )
    assessments: list[ModelRiskAssessment] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """转换为字典"""
        return {
            "total_models_with_save": self.total_models_with_save,
            "total_violations": self.total_violations,
            "risk_counts": self.risk_counts,
            "assessments": [a.to_dict() for a in self.assessments],
        }


# ── 风险评估逻辑 ────────────────────────────────────────────


def _has_external_service_call(analysis: SaveMethodAnalysis) -> bool:
    """
    判断分析结果中是否包含外部服务调用。

    Args:
        analysis: save() 方法分析结果

    Returns:
        True 表示包含外部服务调用
    """
    for summary in analysis.business_logic_summary:
        for keyword in _EXTERNAL_SERVICE_KEYWORDS:
            if keyword in summary:
                return True
    return False


def assess_risk(analysis: SaveMethodAnalysis) -> ModelRiskAssessment:
    """
    根据 SaveMethodAnalysis 评估风险等级。

    规则：
    - 低风险：0 个业务逻辑块
    - 中风险：1-2 个业务逻辑块（且无外部服务调用）
    - 高风险：3+ 个业务逻辑块 或 包含外部服务调用

    Args:
        analysis: save() 方法分析结果

    Returns:
        ModelRiskAssessment 风险评估
    """
    biz_blocks = [b for b in analysis.blocks if b.block_type == BLOCK_BUSINESS_LOGIC]
    biz_count: int = len(biz_blocks)
    has_ext_svc: bool = _has_external_service_call(analysis)

    if biz_count == 0:
        risk_level = RISK_LOW
    elif biz_count >= 3 or has_ext_svc:
        risk_level = RISK_HIGH
    else:
        risk_level = RISK_MEDIUM

    return ModelRiskAssessment(
        model_name=analysis.model_name,
        file_path=analysis.file_path,
        risk_level=risk_level,
        business_logic_count=biz_count,
        business_logic_summary=list(analysis.business_logic_summary),
        has_external_service_call=has_ext_svc,
        total_blocks=len(analysis.blocks),
        extraction_recommendations=list(analysis.extraction_recommendations),
    )


# ── 扫描与报告 ──────────────────────────────────────────────


def _collect_model_files(target_dir: Path) -> list[Path]:
    """
    收集目标目录下所有 Model 层 Python 文件。

    匹配条件（满足任一即可）：
    - 文件位于 models/ 目录下
    - 文件名为 models.py

    排除 migrations、__pycache__、venv 等目录。

    Args:
        target_dir: 要扫描的根目录

    Returns:
        排序后的 Model 文件路径列表
    """
    exclude_dirs: frozenset[str] = frozenset(
        {
            "__pycache__",
            ".git",
            ".tox",
            ".mypy_cache",
            ".pytest_cache",
            "node_modules",
            "migrations",
            "venv",
            ".venv",
        }
    )

    model_files: list[Path] = []
    for py_file in sorted(target_dir.rglob("*.py")):
        if any(part in exclude_dirs for part in py_file.parts):
            continue
        if "models" in py_file.parts or py_file.name == "models.py":
            model_files.append(py_file)

    return model_files


def scan_model_violations(target_dir: Path) -> ModelViolationReport:
    """
    扫描目标目录下所有 Model 层违规并生成风险评估报告。

    流程：
    1. 使用 ModelLayerScanner 扫描业务逻辑违规（用于统计）
    2. 收集所有 Model 文件，使用 SaveMethodAnalyzer 逐文件分析
    3. 对每个包含 save() 覆写的 Model 进行风险评估
    4. 汇总生成报告

    Args:
        target_dir: 要扫描的根目录（通常为 backend/apps）

    Returns:
        ModelViolationReport 完整报告
    """
    report = ModelViolationReport()

    # 步骤1: 使用 ModelLayerScanner 扫描业务逻辑违规（参考数据）
    logger.info("=== 步骤1: 扫描 Model 层 save() 业务逻辑违规 ===")
    scanner = ModelLayerScanner()
    violations: list[Violation] = scanner.scan_directory(target_dir)
    report.total_violations = len(violations)
    logger.info("ModelLayerScanner 检测到 %d 个业务逻辑违规", len(violations))

    # 步骤2: 收集所有 Model 文件，直接用 SaveMethodAnalyzer 分析
    logger.info("=== 步骤2: 分析所有 Model 文件中的 save() 覆写 ===")
    model_files = _collect_model_files(target_dir)
    logger.info("找到 %d 个 Model 层文件", len(model_files))

    analyzer = SaveMethodAnalyzer()
    all_analyses: list[SaveMethodAnalysis] = []

    for model_file in model_files:
        analyses = analyzer.analyze_file(model_file)
        all_analyses.extend(analyses)

    report.total_models_with_save = len(all_analyses)
    logger.info(
        "发现 %d 个包含 save() 覆写的 Model",
        len(all_analyses),
    )

    # 步骤3: 风险评估
    logger.info("=== 步骤3: 风险评估 ===")
    # 计算项目根目录，用于生成相对路径
    project_root = target_dir.parent.parent  # backend/apps -> 项目根
    for analysis in all_analyses:
        # 将绝对路径转为相对路径
        try:
            analysis.file_path = str(Path(analysis.file_path).relative_to(project_root))
        except ValueError:
            pass  # 保留原路径
        assessment = assess_risk(analysis)
        report.assessments.append(assessment)
        report.risk_counts[assessment.risk_level] += 1

    # 按风险等级排序：高 → 中 → 低
    risk_order: dict[str, int] = {RISK_HIGH: 0, RISK_MEDIUM: 1, RISK_LOW: 2}
    report.assessments.sort(key=lambda a: risk_order.get(a.risk_level, 99))

    return report


def print_report(report: ModelViolationReport) -> None:
    """
    将报告输出到日志。

    Args:
        report: Model层违规扫描报告
    """
    logger.info("=" * 60)
    logger.info("Model层违规扫描报告")
    logger.info("=" * 60)
    logger.info("包含 save() 覆写的 Model 总数: %d", report.total_models_with_save)
    logger.info("扫描器检测到的违规总数: %d", report.total_violations)
    logger.info("-" * 40)
    logger.info("风险分布:")
    logger.info("  高风险: %d", report.risk_counts.get(RISK_HIGH, 0))
    logger.info("  中风险: %d", report.risk_counts.get(RISK_MEDIUM, 0))
    logger.info("  低风险: %d", report.risk_counts.get(RISK_LOW, 0))
    logger.info("-" * 40)

    for assessment in report.assessments:
        logger.info(
            "[%s] %s (%s)",
            assessment.risk_level,
            assessment.model_name,
            assessment.file_path,
        )
        logger.info(
            "  业务逻辑块: %d, 总代码块: %d, 外部服务调用: %s",
            assessment.business_logic_count,
            assessment.total_blocks,
            "是" if assessment.has_external_service_call else "否",
        )
        if assessment.business_logic_summary:
            for summary in assessment.business_logic_summary:
                logger.info("  - %s", summary)
        if assessment.extraction_recommendations:
            for rec in assessment.extraction_recommendations:
                logger.info("  建议: %s", rec)
        logger.info("")

    logger.info("=" * 60)


def write_json_report(report: ModelViolationReport, output_dir: Path) -> Path:
    """
    将报告写入 JSON 文件。

    Args:
        report: Model层违规扫描报告
        output_dir: 输出目录

    Returns:
        JSON 文件路径
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "model_violations_report.json"
    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("JSON 报告已写入: %s", json_path)
    return json_path


def main() -> None:
    """扫描入口函数。"""
    setup_logging()

    target_dir = _BACKEND_APPS_DIR.resolve()
    output_dir = _OUTPUT_DIR.resolve()

    logger.info("扫描目标目录: %s", target_dir)

    if not target_dir.is_dir():
        logger.error("目标目录不存在: %s", target_dir)
        return

    report = scan_model_violations(target_dir)
    print_report(report)
    write_json_report(report, output_dir)

    logger.info("扫描完成")


if __name__ == "__main__":
    main()
