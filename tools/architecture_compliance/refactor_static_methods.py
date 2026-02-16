"""
静态方法重构脚本

读取 static_method_analysis.json 中标记为 CONVERT 的方法，
逐文件执行转换并更新调用点。

用法:
    python -m tools.architecture_compliance.refactor_static_methods [--dry-run]
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .call_site_updater import CallSiteUpdater, CallSiteUpdateReport
from .logging_config import get_logger, setup_logging
from .models import RefactoringResult
from .static_method_analyzer import ConversionReason, StaticMethodClassification, StaticMethodInfo
from .static_method_converter import StaticMethodConverter

logger = get_logger("refactor_static_methods")

# ── 常量 ────────────────────────────────────────────────────

_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
_BACKEND_ROOT: Path = _PROJECT_ROOT / "backend" / "apps"
_BACKEND_TESTS: Path = _PROJECT_ROOT / "backend" / "tests"

# 需要扫描调用点的所有目录
_SCAN_ROOTS: list[Path] = [_BACKEND_ROOT, _BACKEND_TESTS]
_ANALYSIS_FILE: Path = _PROJECT_ROOT / "tools" / "architecture_compliance" / "output" / "static_method_analysis.json"
_OUTPUT_DIR: Path = _PROJECT_ROOT / "tools" / "architecture_compliance" / "output"


# ── 数据模型 ────────────────────────────────────────────────


@dataclass
class FileRefactoringReport:
    """单个文件的重构报告"""

    file_path: str
    methods_converted: list[str] = field(default_factory=list)
    conversion_result: RefactoringResult | None = None
    call_site_report: CallSiteUpdateReport | None = None
    ast_valid: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class RefactoringReport:
    """整体重构报告"""

    timestamp: str = ""
    dry_run: bool = False
    total_methods: int = 0
    methods_converted: int = 0
    methods_failed: int = 0
    call_sites_updated: int = 0
    files_processed: list[FileRefactoringReport] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── 核心逻辑 ────────────────────────────────────────────────


def _load_analysis() -> dict[str, Any]:
    """加载静态方法分析结果"""
    if not _ANALYSIS_FILE.exists():
        raise FileNotFoundError(f"分析文件不存在: {_ANALYSIS_FILE}")

    text: str = _ANALYSIS_FILE.read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


def _build_methods_by_file(
    priority_list: list[dict[str, Any]],
) -> dict[str, list[StaticMethodInfo]]:
    """
    将分析结果按文件分组，构建 StaticMethodInfo 列表。

    Returns:
        {file_path: [StaticMethodInfo, ...]}
    """
    by_file: dict[str, list[StaticMethodInfo]] = {}

    for item in priority_list:
        file_path: str = item["file_path"]
        reasons: list[ConversionReason] = [
            ConversionReason(rule=r["rule"], detail=r["detail"]) for r in item.get("reasons", [])
        ]
        info = StaticMethodInfo(
            class_name=item["class_name"],
            method_name=item["method_name"],
            file_path=file_path,
            line_number=item["line_number"],
            classification=StaticMethodClassification.CONVERT,
            reasons=reasons,
            code_snippet=item.get("code_snippet", ""),
        )
        by_file.setdefault(file_path, []).append(info)

    return by_file


def _verify_ast(file_path: Path) -> bool:
    """验证文件 AST 是否合法"""
    try:
        source: str = file_path.read_text(encoding="utf-8")
        ast.parse(source)
        return True
    except SyntaxError as exc:
        logger.error("AST 验证失败 %s (行 %s): %s", file_path, exc.lineno, exc.msg)
        return False


def _process_single_file(
    file_path: Path,
    methods: list[StaticMethodInfo],
    converter: StaticMethodConverter,
    updater: CallSiteUpdater,
    *,
    dry_run: bool = False,
) -> FileRefactoringReport:
    """
    处理单个文件：转换静态方法 + 更新调用点 + AST 验证。

    Args:
        file_path: 目标文件
        methods: 该文件中需要转换的方法列表
        converter: 转换器实例
        updater: 调用点更新器实例
        dry_run: 为 True 时不写入文件

    Returns:
        FileRefactoringReport
    """
    report = FileRefactoringReport(file_path=str(file_path))
    method_names: list[str] = [f"{m.class_name}.{m.method_name}" for m in methods]
    report.methods_converted = method_names

    logger.info(
        "处理文件: %s (%d 个方法: %s)",
        file_path.name,
        len(methods),
        ", ".join(method_names),
    )

    # 步骤 1: 转换静态方法
    result: RefactoringResult = converter.convert_file(
        file_path,
        methods,
        dry_run=dry_run,
    )
    report.conversion_result = result

    if not result.success:
        msg: str = f"转换失败: {result.error_message}"
        logger.error(msg)
        report.errors.append(msg)
        return report

    for change in result.changes_made:
        logger.info("  变更: %s", change)

    # 步骤 2: 更新调用点（扫描 apps 和 tests 目录）
    combined_call_report = CallSiteUpdateReport()
    for scan_root in _SCAN_ROOTS:
        if not scan_root.exists():
            continue
        sub_report: CallSiteUpdateReport = updater.update_call_sites_for_methods(
            scan_root,
            methods,
            exclude_file=file_path,
            dry_run=dry_run,
        )
        combined_call_report.total_files_scanned += sub_report.total_files_scanned
        combined_call_report.total_call_sites_found += sub_report.total_call_sites_found
        combined_call_report.total_call_sites_updated += sub_report.total_call_sites_updated
        combined_call_report.file_reports.extend(sub_report.file_reports)
        combined_call_report.results.extend(sub_report.results)

    report.call_site_report = combined_call_report

    logger.info(
        "  调用点: 找到 %d, 更新 %d",
        combined_call_report.total_call_sites_found,
        combined_call_report.total_call_sites_updated,
    )

    for fr in combined_call_report.file_reports:
        for change in fr.changes:
            logger.info("    %s: %s", Path(fr.file_path).name, change)
        for err in fr.errors:
            logger.warning("    %s: %s", Path(fr.file_path).name, err)
            report.errors.append(f"{fr.file_path}: {err}")

    # 步骤 3: AST 验证（转换后的文件）
    if not dry_run:
        report.ast_valid = _verify_ast(file_path)
        if not report.ast_valid:
            report.errors.append(f"AST 验证失败: {file_path}")

        # 验证被更新的调用点文件
        for fr in combined_call_report.file_reports:
            if fr.call_sites_updated > 0:
                cs_path = Path(fr.file_path)
                if not _verify_ast(cs_path):
                    report.errors.append(f"调用点文件 AST 验证失败: {cs_path}")
    else:
        report.ast_valid = True

    return report


def run_refactoring(*, dry_run: bool = False) -> RefactoringReport:
    """
    执行完整的静态方法重构流程。

    Args:
        dry_run: 为 True 时不写入文件

    Returns:
        RefactoringReport
    """
    report = RefactoringReport(
        timestamp=datetime.now().isoformat(),
        dry_run=dry_run,
    )

    # 加载分析结果
    analysis: dict[str, Any] = _load_analysis()
    priority_list: list[dict[str, Any]] = analysis.get("priority_list", [])

    if not priority_list:
        logger.info("没有需要转换的静态方法")
        return report

    report.total_methods = len(priority_list)
    logger.info("共 %d 个方法需要转换", report.total_methods)

    # 按文件分组
    by_file: dict[str, list[StaticMethodInfo]] = _build_methods_by_file(
        priority_list,
    )

    converter = StaticMethodConverter()
    updater = CallSiteUpdater()

    # 逐文件处理
    for file_path_str, methods in by_file.items():
        file_path = Path(file_path_str)

        if not file_path.exists():
            msg = f"文件不存在，跳过: {file_path}"
            logger.warning(msg)
            report.errors.append(msg)
            report.methods_failed += len(methods)
            continue

        file_report: FileRefactoringReport = _process_single_file(
            file_path,
            methods,
            converter,
            updater,
            dry_run=dry_run,
        )
        report.files_processed.append(file_report)

        if file_report.errors:
            report.methods_failed += len(methods)
        else:
            report.methods_converted += len(methods)

        if file_report.call_site_report is not None:
            report.call_sites_updated += file_report.call_site_report.total_call_sites_updated

    # 汇总
    logger.info("=" * 60)
    logger.info("重构完成:")
    logger.info("  总方法数: %d", report.total_methods)
    logger.info("  成功转换: %d", report.methods_converted)
    logger.info("  失败: %d", report.methods_failed)
    logger.info("  调用点更新: %d", report.call_sites_updated)
    logger.info("  dry_run: %s", report.dry_run)

    if report.errors:
        logger.warning("错误汇总:")
        for err in report.errors:
            logger.warning("  - %s", err)

    # 保存报告
    _save_report(report)

    return report


def _save_report(report: RefactoringReport) -> None:
    """保存重构报告到 JSON 文件"""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path: Path = _OUTPUT_DIR / "static_method_refactoring_report.json"

    # 构建可序列化的数据
    data: dict[str, Any] = {
        "timestamp": report.timestamp,
        "dry_run": report.dry_run,
        "total_methods": report.total_methods,
        "methods_converted": report.methods_converted,
        "methods_failed": report.methods_failed,
        "call_sites_updated": report.call_sites_updated,
        "errors": report.errors,
        "files_processed": [],
    }

    for fr in report.files_processed:
        file_data: dict[str, Any] = {
            "file_path": fr.file_path,
            "methods_converted": fr.methods_converted,
            "ast_valid": fr.ast_valid,
            "errors": fr.errors,
        }
        if fr.conversion_result is not None:
            file_data["conversion_result"] = fr.conversion_result.to_dict()
        if fr.call_site_report is not None:
            file_data["call_site_summary"] = {
                "found": fr.call_site_report.total_call_sites_found,
                "updated": fr.call_site_report.total_call_sites_updated,
            }
        data["files_processed"].append(file_data)

    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("报告已保存: %s", output_path)


# ── 入口 ────────────────────────────────────────────────────


def main() -> None:
    """命令行入口"""
    setup_logging()

    dry_run: bool = "--dry-run" in sys.argv

    if dry_run:
        logger.info("=== DRY RUN 模式 ===")

    report: RefactoringReport = run_refactoring(dry_run=dry_run)

    if report.methods_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
