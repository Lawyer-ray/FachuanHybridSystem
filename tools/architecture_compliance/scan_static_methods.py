"""
Service层静态方法扫描与分类脚本

扫描 backend/apps/ 下所有 Service 文件中的 @staticmethod，
使用 StaticMethodAnalyzer 进行分类（CONVERT / KEEP），
生成优先级列表并输出 JSON 报告。

用法:
    python -m tools.architecture_compliance.scan_static_methods
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .logging_config import get_logger, setup_logging
from .static_method_analyzer import (
    StaticMethodAnalysisReport,
    StaticMethodAnalyzer,
    StaticMethodClassification,
    StaticMethodInfo,
)

logger = get_logger("scan_static_methods")

_BACKEND_APPS_DIR: Path = Path("backend/apps")
_OUTPUT_DIR: Path = Path("tools/architecture_compliance/output")
_OUTPUT_FILE: str = "static_method_analysis.json"

# 优先级权重：convert 原因越多，优先级越高
_PRIORITY_WEIGHTS: dict[str, int] = {
    "import_in_body": 3,
    "calls_class_method": 2,
    "model_objects_access": 4,
    "instantiates_self_class": 2,
    "accesses_settings": 1,
    "calls_external_service": 3,
}


def _compute_priority(method: StaticMethodInfo) -> int:
    """
    计算单个方法的重构优先级分数。

    分数越高，越应该优先重构。

    Args:
        method: 静态方法分析结果

    Returns:
        优先级分数
    """
    if not method.should_convert:
        return 0
    score: int = 0
    for reason in method.reasons:
        score += _PRIORITY_WEIGHTS.get(reason.rule, 1)
    return score


def _build_priority_list(
    methods: list[StaticMethodInfo],
) -> list[dict[str, Any]]:
    """
    生成按优先级排序的重构列表（仅包含 CONVERT 方法）。

    Args:
        methods: 所有静态方法分析结果

    Returns:
        按优先级降序排列的方法列表
    """
    convert_items: list[dict[str, Any]] = []
    for m in methods:
        if not m.should_convert:
            continue
        priority = _compute_priority(m)
        convert_items.append({
            "class_name": m.class_name,
            "method_name": m.method_name,
            "file_path": m.file_path,
            "line_number": m.line_number,
            "priority_score": priority,
            "reasons": [
                {"rule": r.rule, "detail": r.detail} for r in m.reasons
            ],
            "code_snippet": m.code_snippet,
        })
    convert_items.sort(key=lambda x: x["priority_score"], reverse=True)
    return convert_items


def _build_keep_list(
    methods: list[StaticMethodInfo],
) -> list[dict[str, Any]]:
    """
    生成保留为静态方法的列表。

    Args:
        methods: 所有静态方法分析结果

    Returns:
        保留方法列表
    """
    keep_items: list[dict[str, Any]] = []
    for m in methods:
        if m.should_convert:
            continue
        keep_items.append({
            "class_name": m.class_name,
            "method_name": m.method_name,
            "file_path": m.file_path,
            "line_number": m.line_number,
            "reasons": [
                {"rule": r.rule, "detail": r.detail} for r in m.reasons
            ],
            "code_snippet": m.code_snippet,
        })
    return keep_items


def _build_report_dict(report: StaticMethodAnalysisReport) -> dict[str, Any]:
    """
    将分析报告转换为可序列化的字典。

    Args:
        report: 分析报告

    Returns:
        JSON 可序列化的字典
    """
    priority_list = _build_priority_list(report.methods)
    keep_list = _build_keep_list(report.methods)

    # 按文件统计
    file_stats: dict[str, dict[str, int]] = {}
    for m in report.methods:
        fp = m.file_path
        if fp not in file_stats:
            file_stats[fp] = {"convert": 0, "keep": 0}
        if m.should_convert:
            file_stats[fp]["convert"] += 1
        else:
            file_stats[fp]["keep"] += 1

    # 按类统计
    class_stats: dict[str, dict[str, int]] = {}
    for m in report.methods:
        key = f"{m.file_path}::{m.class_name}"
        if key not in class_stats:
            class_stats[key] = {"convert": 0, "keep": 0}
        if m.should_convert:
            class_stats[key]["convert"] += 1
        else:
            class_stats[key]["keep"] += 1

    return {
        "scan_timestamp": datetime.now().isoformat(),
        "target_directory": str(_BACKEND_APPS_DIR.resolve()),
        "summary": {
            "total_static_methods": report.total,
            "convert_count": report.convert_count,
            "keep_count": report.keep_count,
        },
        "priority_list": priority_list,
        "keep_list": keep_list,
        "file_stats": file_stats,
        "class_stats": class_stats,
    }


def _write_json(data: dict[str, Any], output_path: Path) -> None:
    """
    将报告写入 JSON 文件。

    Args:
        data: 报告数据
        output_path: 输出文件路径
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("报告已写入: %s", output_path)


def _log_summary(report: StaticMethodAnalysisReport) -> None:
    """
    输出分析摘要日志。

    Args:
        report: 分析报告
    """
    logger.info("=" * 60)
    logger.info("静态方法扫描结果摘要")
    logger.info("=" * 60)
    logger.info("总计: %d 个静态方法", report.total)
    logger.info("需要转换 (CONVERT): %d 个", report.convert_count)
    logger.info("建议保留 (KEEP): %d 个", report.keep_count)
    logger.info("-" * 60)

    if report.convert_methods:
        logger.info("--- 需要转换的方法 (按优先级) ---")
        scored = [
            (_compute_priority(m), m) for m in report.convert_methods
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        for score, m in scored:
            logger.info(
                "  [优先级=%d] %s.%s (%s:%d)",
                score,
                m.class_name,
                m.method_name,
                m.file_path,
                m.line_number,
            )
            for r in m.reasons:
                logger.info("    - %s: %s", r.rule, r.detail)

    if report.keep_methods:
        logger.info("--- 保留为静态方法 ---")
        for m in report.keep_methods:
            logger.info(
                "  %s.%s (%s:%d)",
                m.class_name,
                m.method_name,
                m.file_path,
                m.line_number,
            )
            for r in m.reasons:
                logger.info("    - %s: %s", r.rule, r.detail)


def main() -> None:
    """扫描入口函数。"""
    setup_logging()

    target_dir = _BACKEND_APPS_DIR.resolve()
    output_dir = _OUTPUT_DIR.resolve()
    output_file = output_dir / _OUTPUT_FILE

    logger.info("开始扫描静态方法: %s", target_dir)

    if not target_dir.is_dir():
        logger.error("目标目录不存在: %s", target_dir)
        return

    analyzer = StaticMethodAnalyzer()
    report = analyzer.analyze_directory(target_dir)

    _log_summary(report)

    report_data = _build_report_dict(report)
    _write_json(report_data, output_file)

    logger.info("扫描完成，结果已保存到: %s", output_file)


if __name__ == "__main__":
    main()
