"""
架构合规性扫描运行器

在真实backend代码上运行所有三个扫描器（API层、Service层、Model层），
生成合并报告并输出到 tools/architecture_compliance/output/ 目录。
"""
from __future__ import annotations

from pathlib import Path

from .api_scanner import ApiLayerScanner
from .logging_config import get_logger, setup_logging
from .model_scanner import ModelLayerScanner
from .models import Violation
from .report_generator import ReportGenerator
from .service_scanner import ServiceLayerScanner

logger = get_logger("run_scan")

# 项目路径常量
_BACKEND_APPS_DIR: Path = Path("backend/apps")
_OUTPUT_DIR: Path = Path("tools/architecture_compliance/output")


def run_all_scanners(target_dir: Path) -> list[Violation]:
    """
    运行所有三个扫描器并合并结果。

    Args:
        target_dir: 要扫描的目标目录

    Returns:
        合并后的违规列表
    """
    all_violations: list[Violation] = []

    # 1. API层扫描
    logger.info("=== 开始API层扫描 ===")
    api_scanner = ApiLayerScanner()
    api_violations = api_scanner.scan_directory(target_dir)
    all_violations.extend(api_violations)
    logger.info("API层扫描完成: %d 个违规", len(api_violations))

    # 2. Service层扫描
    logger.info("=== 开始Service层扫描 ===")
    service_scanner = ServiceLayerScanner()
    service_violations = service_scanner.scan_directory(target_dir)
    all_violations.extend(service_violations)
    logger.info("Service层扫描完成: %d 个违规", len(service_violations))

    # 3. Model层扫描
    logger.info("=== 开始Model层扫描 ===")
    model_scanner = ModelLayerScanner()
    model_violations = model_scanner.scan_directory(target_dir)
    all_violations.extend(model_violations)
    logger.info("Model层扫描完成: %d 个违规", len(model_violations))

    return all_violations


def main() -> None:
    """扫描入口函数。"""
    setup_logging()

    target_dir = _BACKEND_APPS_DIR.resolve()
    output_dir = _OUTPUT_DIR.resolve()

    logger.info("扫描目标目录: %s", target_dir)
    logger.info("报告输出目录: %s", output_dir)

    if not target_dir.is_dir():
        logger.error("目标目录不存在: %s", target_dir)
        return

    # 运行所有扫描器
    all_violations = run_all_scanners(target_dir)

    logger.info("=== 扫描汇总 ===")
    logger.info("总违规数: %d", len(all_violations))

    # 生成报告
    generator = ReportGenerator()
    report = generator.build_report(all_violations)
    json_path, md_path = generator.write_reports(report, output_dir)

    logger.info("JSON报告: %s", json_path)
    logger.info("Markdown报告: %s", md_path)
    logger.info("扫描完成")


if __name__ == "__main__":
    main()
