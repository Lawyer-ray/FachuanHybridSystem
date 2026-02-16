"""
试点模块扫描器

针对指定模块运行所有架构违规扫描器（API层、Service层、Model层），
生成模块级别的违规报告。用于Phase 1试点模块评估。

用法:
    # 作为模块运行
    python -m tools.architecture_compliance.scan_pilot_module [module_name]

    # 默认扫描 contracts 模块
    python -m tools.architecture_compliance.scan_pilot_module
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from .api_scanner import ApiLayerScanner
from .logging_config import get_logger, setup_logging
from .model_scanner import ModelLayerScanner
from .models import Violation
from .report_generator import ReportGenerator
from .service_scanner import ServiceLayerScanner

logger = get_logger("scan_pilot_module")

# 项目路径常量
_BACKEND_APPS_DIR: Path = Path("backend/apps")
_OUTPUT_DIR: Path = Path("tools/architecture_compliance/output")

# 默认试点模块
_DEFAULT_PILOT_MODULE: str = "contracts"


def _resolve_module_path(module_name: str) -> Optional[Path]:
    """
    解析模块路径并验证其存在性。

    Args:
        module_name: apps下的模块名称（如 "contracts"）

    Returns:
        模块的绝对路径，不存在时返回 None
    """
    module_path: Path = (_BACKEND_APPS_DIR / module_name).resolve()
    if not module_path.is_dir():
        logger.error("模块目录不存在: %s", module_path)
        return None
    return module_path


def scan_module(module_name: str) -> list[Violation]:
    """
    对指定模块运行所有三个扫描器并合并结果。

    Args:
        module_name: apps下的模块名称（如 "contracts"）

    Returns:
        合并后的违规列表
    """
    module_path = _resolve_module_path(module_name)
    if module_path is None:
        return []

    logger.info("===== 试点模块扫描: %s =====", module_name)
    logger.info("模块路径: %s", module_path)

    all_violations: list[Violation] = []

    # 1. API层扫描
    logger.info("--- API层扫描 ---")
    api_scanner = ApiLayerScanner()
    api_violations = api_scanner.scan_directory(module_path)
    all_violations.extend(api_violations)
    logger.info("API层违规: %d 个", len(api_violations))

    # 2. Service层扫描
    logger.info("--- Service层扫描 ---")
    service_scanner = ServiceLayerScanner()
    service_violations = service_scanner.scan_directory(module_path)
    all_violations.extend(service_violations)
    logger.info("Service层违规: %d 个", len(service_violations))

    # 3. Model层扫描
    logger.info("--- Model层扫描 ---")
    model_scanner = ModelLayerScanner()
    model_violations = model_scanner.scan_directory(module_path)
    all_violations.extend(model_violations)
    logger.info("Model层违规: %d 个", len(model_violations))

    logger.info("===== 扫描汇总: %s 模块共 %d 个违规 =====", module_name, len(all_violations))
    return all_violations


def _log_scan_summary(module_name: str, violations: list[Violation]) -> None:
    """
    输出扫描结果的分类摘要日志。

    Args:
        module_name: 模块名称
        violations: 违规列表
    """
    api_count: int = 0
    cross_import_count: int = 0
    static_method_count: int = 0
    model_count: int = 0

    for v in violations:
        if v.violation_type == "api_direct_orm_access":
            api_count += 1
        elif v.violation_type == "service_cross_module_import":
            cross_import_count += 1
        elif v.violation_type == "service_static_method_abuse":
            static_method_count += 1
        elif v.violation_type == "model_business_logic_in_save":
            model_count += 1

    logger.info("===== %s 模块违规分类摘要 =====", module_name)
    logger.info("  API层直接ORM访问:       %d", api_count)
    logger.info("  Service层跨模块导入:     %d", cross_import_count)
    logger.info("  Service层静态方法滥用:   %d", static_method_count)
    logger.info("  Model层save()业务逻辑:  %d", model_count)
    logger.info("  总计:                    %d", len(violations))

    if api_count == 0:
        logger.info("✓ contracts模块API层无违规，无需API层重构")
    if len(violations) == 0:
        logger.info("✓ %s 模块无任何架构违规", module_name)


def main() -> None:
    """试点模块扫描入口函数。"""
    setup_logging()

    # 从命令行参数获取模块名，默认为 contracts
    module_name: str = _DEFAULT_PILOT_MODULE
    if len(sys.argv) > 1:
        module_name = sys.argv[1]

    output_dir: Path = _OUTPUT_DIR.resolve()
    logger.info("试点模块: %s", module_name)
    logger.info("报告输出目录: %s", output_dir)

    # 运行扫描
    violations = scan_module(module_name)

    # 输出分类摘要
    _log_scan_summary(module_name, violations)

    # 生成报告
    generator = ReportGenerator()
    report = generator.build_report(violations)
    base_name: str = f"pilot_{module_name}_violations"
    json_path, md_path = generator.write_reports(report, output_dir, base_name=base_name)

    logger.info("JSON报告: %s", json_path)
    logger.info("Markdown报告: %s", md_path)
    logger.info("试点模块扫描完成")


if __name__ == "__main__":
    main()
