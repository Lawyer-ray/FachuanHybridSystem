"""
静态方法重构总结报告生成器

读取扫描分析结果和重构报告，合并生成包含完整统计的JSON摘要。
输出路径: tools/architecture_compliance/output/static_method_summary.json

Requirements: 5.5
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 将项目根目录加入 sys.path，以便直接运行脚本
_SCRIPT_DIR: Path = Path(__file__).resolve().parent
_PROJECT_ROOT: Path = _SCRIPT_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.architecture_compliance.logging_config import get_logger, setup_logging

logger = get_logger("generate_static_method_report")

# ── 常量 ────────────────────────────────────────────────────

_OUTPUT_DIR: Path = _SCRIPT_DIR / "output"
_ANALYSIS_FILE: Path = _OUTPUT_DIR / "static_method_analysis.json"
_REFACTORING_FILE: Path = _OUTPUT_DIR / "static_method_refactoring_report.json"
_OUTPUT_FILE: Path = _OUTPUT_DIR / "static_method_summary.json"


def _load_json(file_path: Path) -> dict[str, Any]:
    """
    加载JSON文件。

    Args:
        file_path: JSON文件路径

    Returns:
        解析后的字典

    Raises:
        FileNotFoundError: 文件不存在
        json.JSONDecodeError: JSON格式错误
    """
    logger.info("加载文件: %s", file_path)
    content: str = file_path.read_text(encoding="utf-8")
    return json.loads(content)


def _strip_project_prefix(file_path: str) -> str:
    """
    将绝对路径转换为相对于项目根目录的路径。

    Args:
        file_path: 可能是绝对路径的文件路径

    Returns:
        相对路径字符串
    """
    path = Path(file_path)
    try:
        return str(path.relative_to(_PROJECT_ROOT))
    except ValueError:
        return file_path


def _build_converted_methods(
    refactoring_data: dict[str, Any],
    analysis_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    构建已转换方法的详情列表。

    从重构报告中提取每个已转换方法的信息，
    并从分析数据中补充转换原因。

    Args:
        refactoring_data: 重构报告数据
        analysis_data: 扫描分析数据

    Returns:
        已转换方法详情列表
    """
    # 建立 "ClassName.method_name" -> priority_item 的索引
    priority_index: dict[str, dict[str, Any]] = {}
    for item in analysis_data.get("priority_list", []):
        key: str = f"{item['class_name']}.{item['method_name']}"
        priority_index[key] = item

    converted: list[dict[str, Any]] = []
    for file_info in refactoring_data.get("files_processed", []):
        file_path: str = _strip_project_prefix(file_info["file_path"])
        for method_ref in file_info.get("methods_converted", []):
            # method_ref 格式: "ClassName.method_name"
            priority_item: dict[str, Any] | None = priority_index.get(method_ref)
            reasons: list[str] = []
            if priority_item:
                reasons = [r["detail"] for r in priority_item.get("reasons", [])]

            class_name: str = method_ref.split(".")[0] if "." in method_ref else ""
            method_name: str = method_ref.split(".")[1] if "." in method_ref else method_ref

            converted.append(
                {
                    "class_name": class_name,
                    "method_name": method_name,
                    "file_path": file_path,
                    "reasons": reasons,
                    "changes": file_info.get("conversion_result", {}).get("changes_made", []),
                }
            )

    return converted


def _build_kept_methods(analysis_data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    构建保留的静态方法详情列表。

    Args:
        analysis_data: 扫描分析数据

    Returns:
        保留方法详情列表
    """
    kept: list[dict[str, Any]] = []
    for item in analysis_data.get("keep_list", []):
        reasons: list[str] = [r["detail"] for r in item.get("reasons", [])]
        kept.append(
            {
                "class_name": item["class_name"],
                "method_name": item["method_name"],
                "file_path": _strip_project_prefix(item["file_path"]),
                "reasons_for_keeping": reasons,
            }
        )
    return kept


def _collect_errors(refactoring_data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    收集重构过程中遇到的错误。

    Args:
        refactoring_data: 重构报告数据

    Returns:
        错误详情列表
    """
    errors: list[dict[str, Any]] = []

    # 顶层错误
    for err in refactoring_data.get("errors", []):
        errors.append({"source": "global", "detail": err})

    # 每个文件的错误
    for file_info in refactoring_data.get("files_processed", []):
        file_path: str = _strip_project_prefix(file_info["file_path"])
        for err in file_info.get("errors", []):
            errors.append({"source": file_path, "detail": err})

    return errors


def _build_summary(
    analysis_data: dict[str, Any],
    refactoring_data: dict[str, Any],
) -> dict[str, Any]:
    """
    构建静态方法重构总结报告。

    Args:
        analysis_data: 扫描分析数据
        refactoring_data: 重构报告数据

    Returns:
        完整的报告字典
    """
    analysis_summary: dict[str, Any] = analysis_data.get("summary", {})
    total: int = analysis_summary.get("total_static_methods", 0)
    convert_count: int = analysis_summary.get("convert_count", 0)
    keep_count: int = analysis_summary.get("keep_count", 0)

    methods_converted: int = refactoring_data.get("methods_converted", 0)
    methods_failed: int = refactoring_data.get("methods_failed", 0)
    call_sites_updated: int = refactoring_data.get("call_sites_updated", 0)

    converted_details: list[dict[str, Any]] = _build_converted_methods(
        refactoring_data,
        analysis_data,
    )
    kept_details: list[dict[str, Any]] = _build_kept_methods(analysis_data)
    errors: list[dict[str, Any]] = _collect_errors(refactoring_data)

    summary: dict[str, Any] = {
        "report_title": "静态方法重构总结报告",
        "generated_at": datetime.now().isoformat(),
        "scan_timestamp": analysis_data.get("scan_timestamp", ""),
        "refactoring_timestamp": refactoring_data.get("timestamp", ""),
        "overview": {
            "total_static_methods_found": total,
            "methods_to_convert": convert_count,
            "methods_to_keep": keep_count,
            "methods_converted": methods_converted,
            "methods_failed": methods_failed,
            "call_sites_updated": call_sites_updated,
            "conversion_success_rate_percent": (
                round(methods_converted / convert_count * 100, 1) if convert_count > 0 else 0.0
            ),
            "all_conversions_successful": methods_failed == 0 and methods_converted == convert_count,
        },
        "converted_methods": converted_details,
        "kept_methods": kept_details,
        "errors": errors,
    }
    return summary


def _write_report(summary: dict[str, Any], output_path: Path) -> Path:
    """
    将报告写入JSON文件。

    Args:
        summary: 报告数据字典
        output_path: 输出文件路径

    Returns:
        写入的文件路径
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content: str = json.dumps(summary, ensure_ascii=False, indent=2)
    output_path.write_text(content, encoding="utf-8")
    logger.info("报告已写入: %s", output_path)
    return output_path


def generate_static_method_report(
    analysis_path: Path | None = None,
    refactoring_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """
    生成静态方法重构总结报告。

    1. 读取扫描分析结果
    2. 读取重构报告
    3. 合并生成总结报告
    4. 输出JSON文件

    Args:
        analysis_path: 扫描分析文件路径
        refactoring_path: 重构报告文件路径
        output_path: 输出文件路径

    Returns:
        报告数据字典
    """
    if analysis_path is None:
        analysis_path = _ANALYSIS_FILE
    if refactoring_path is None:
        refactoring_path = _REFACTORING_FILE
    if output_path is None:
        output_path = _OUTPUT_FILE

    logger.info("=== 生成静态方法重构总结报告 ===")

    # 1. 加载输入数据
    analysis_data: dict[str, Any] = _load_json(analysis_path)
    refactoring_data: dict[str, Any] = _load_json(refactoring_path)

    # 2. 构建摘要
    summary: dict[str, Any] = _build_summary(analysis_data, refactoring_data)

    # 3. 写入文件
    _write_report(summary, output_path)

    # 4. 输出关键指标
    overview: dict[str, Any] = summary["overview"]
    logger.info(
        "总计: %d 个静态方法, 转换 %d 个, 保留 %d 个, 失败 %d 个",
        overview["total_static_methods_found"],
        overview["methods_converted"],
        overview["methods_to_keep"],
        overview["methods_failed"],
    )
    logger.info("调用点更新: %d 处", overview["call_sites_updated"])

    if overview["all_conversions_successful"]:
        logger.info("✅ 所有需要转换的静态方法已成功转换")
    else:
        logger.info(
            "⚠️ %d 个方法转换失败",
            overview["methods_failed"],
        )

    return summary


def main() -> None:
    """脚本入口。"""
    setup_logging()
    generate_static_method_report()


if __name__ == "__main__":
    main()
