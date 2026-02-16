#!/usr/bin/env python3
"""
批量修复 document_delivery 模块的简单类型错误
- 修复泛型类型参数缺失 (type-arg)
- 修复返回类型缺失 (no-untyped-def)
- 为所有函数添加类型注解
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def fix_type_arg_errors() -> None:
    """修复泛型类型参数缺失错误"""
    fixes = [
        # court_api/court_document_api_exceptions.py
        (
            "backend/apps/automation/services/document_delivery/court_api/court_document_api_exceptions.py",
            [
                (
                    "def __init__(self, message: str, response_data: dict = None):",
                    "def __init__(self, message: str, response_data: dict[str, Any] | None = None):",
                ),
            ],
        ),
        # court_document_api_client.py
        (
            "backend/apps/automation/services/document_delivery/court_document_api_client.py",
            [
                (
                    "def __init__(self, base_url: str, headers: dict = None):",
                    "def __init__(self, base_url: str, headers: dict[str, Any] | None = None):",
                ),
                (
                    "def query_documents(self, params: dict) -> DocumentQueryResult:",
                    "def query_documents(self, params: dict[str, Any]) -> DocumentQueryResult:",
                ),
                (
                    "def download_document(self, doc_id: str, params: dict) -> bytes:",
                    "def download_document(self, doc_id: str, params: dict[str, Any]) -> bytes:",
                ),
            ],
        ),
        # playwright/page_operations.py
        (
            "backend/apps/automation/services/document_delivery/playwright/page_operations.py",
            [
                (
                    "async def _extract_document_info(self, row) -> tuple:",
                    "async def _extract_document_info(self, row) -> tuple[str, str, str]:",
                ),
            ],
        ),
        # processor/document_delivery_processor.py
        (
            "backend/apps/automation/services/document_delivery/processor/document_delivery_processor.py",
            [
                (
                    "def _parse_document_info(self, info_str: str) -> tuple:",
                    "def _parse_document_info(self, info_str: str) -> tuple[str, str]:",
                ),
            ],
        ),
        # playwright/document_delivery_playwright_service.py
        (
            "backend/apps/automation/services/document_delivery/playwright/document_delivery_playwright_service.py",
            [
                (
                    "async def _extract_document_info(self, row) -> tuple:",
                    "async def _extract_document_info(self, row) -> tuple[str, str, str]:",
                ),
                (
                    "def _parse_document_info(self, info_str: str) -> tuple:",
                    "def _parse_document_info(self, info_str: str) -> tuple[str, str]:",
                ),
            ],
        ),
        # api/document_delivery_api_service.py
        (
            "backend/apps/automation/services/document_delivery/api/document_delivery_api_service.py",
            [
                (
                    "def _parse_document_info(self, info_str: str) -> tuple:",
                    "def _parse_document_info(self, info_str: str) -> tuple[str, str]:",
                ),
            ],
        ),
        # download_service.py
        (
            "backend/apps/automation/services/document_delivery/download_service.py",
            [
                (
                    "def _parse_document_info(self, info_str: str) -> tuple:",
                    "def _parse_document_info(self, info_str: str) -> tuple[str, str]:",
                ),
            ],
        ),
        # document_delivery_service.py
        (
            "backend/apps/automation/services/document_delivery/document_delivery_service.py",
            [
                (
                    "async def _extract_document_info(self, row) -> tuple:",
                    "async def _extract_document_info(self, row) -> tuple[str, str, str]:",
                ),
                (
                    "def _parse_document_info(self, info_str: str) -> tuple:",
                    "def _parse_document_info(self, info_str: str) -> tuple[str, str]:",
                ),
            ],
        ),
    ]

    for file_path, replacements in fixes:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"文件不存在: {file_path}")
            continue

        content = path.read_text(encoding="utf-8")
        modified = False

        for old_str, new_str in replacements:
            if old_str in content:
                content = content.replace(old_str, new_str)
                modified = True
                logger.info(f"修复 {file_path}: {old_str[:50]}...")

        if modified:
            path.write_text(content, encoding="utf-8")
            logger.info(f"已修复文件: {file_path}")


def fix_no_untyped_def_errors() -> None:
    """修复函数缺少类型注解错误"""
    fixes = [
        # coordinator/strategies/api_strategy.py
        (
            "backend/apps/automation/services/document_delivery/coordinator/strategies/api_strategy.py",
            [
                ("def __init__(self, api_service):", "def __init__(self, api_service: Any) -> None:"),
            ],
        ),
        # court_api/court_document_api_coordinator.py
        (
            "backend/apps/automation/services/document_delivery/court_api/court_document_api_coordinator.py",
            [
                ("def __enter__(self):", "def __enter__(self) -> 'CourtDocumentApiCoordinator':"),
                (
                    "def __exit__(self, exc_type, exc_val, exc_tb):",
                    "def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:",
                ),
            ],
        ),
        # processor/document_delivery_processor.py
        (
            "backend/apps/automation/services/document_delivery/processor/document_delivery_processor.py",
            [
                ("def __enter__(self):", "def __enter__(self) -> 'DocumentDeliveryProcessor':"),
                (
                    "def __exit__(self, exc_type, exc_val, exc_tb):",
                    "def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:",
                ),
                (
                    "def _parse_document_info(self, info_str):",
                    "def _parse_document_info(self, info_str: str) -> tuple[str, str]:",
                ),
                ("def _extract_case_info(self, sms):", "def _extract_case_info(self, sms: Any) -> dict[str, Any]:"),
                (
                    "def _create_document_record(self, doc):",
                    "def _create_document_record(self, doc: Any) -> dict[str, Any]:",
                ),
            ],
        ),
        # playwright/document_delivery_playwright_service.py
        (
            "backend/apps/automation/services/document_delivery/playwright/document_delivery_playwright_service.py",
            [
                ("def _extract_case_info(self, sms):", "def _extract_case_info(self, sms: Any) -> dict[str, Any]:"),
                ("def __enter__(self):", "def __enter__(self) -> 'DocumentDeliveryPlaywrightService':"),
                (
                    "def __exit__(self, exc_type, exc_val, exc_tb):",
                    "def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:",
                ),
                (
                    "def _parse_document_info(self, info_str):",
                    "def _parse_document_info(self, info_str: str) -> tuple[str, str]:",
                ),
                (
                    "def _create_document_record(self, doc):",
                    "def _create_document_record(self, doc: Any) -> dict[str, Any]:",
                ),
            ],
        ),
        # api/document_delivery_api_service.py
        (
            "backend/apps/automation/services/document_delivery/api/document_delivery_api_service.py",
            [
                ("def __enter__(self):", "def __enter__(self) -> 'DocumentDeliveryApiService':"),
                (
                    "def __exit__(self, exc_type, exc_val, exc_tb):",
                    "def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:",
                ),
                (
                    "def _parse_document_info(self, info_str):",
                    "def _parse_document_info(self, info_str: str) -> tuple[str, str]:",
                ),
                ("def _extract_case_info(self, sms):", "def _extract_case_info(self, sms: Any) -> dict[str, Any]:"),
                (
                    "def _create_document_record(self, doc):",
                    "def _create_document_record(self, doc: Any) -> dict[str, Any]:",
                ),
            ],
        ),
        # document_delivery_service.py
        (
            "backend/apps/automation/services/document_delivery/document_delivery_service.py",
            [
                ("def _extract_case_info(self, sms):", "def _extract_case_info(self, sms: Any) -> dict[str, Any]:"),
                ("def __enter__(self):", "def __enter__(self) -> 'DocumentDeliveryService':"),
                (
                    "def _parse_document_info(self, info_str):",
                    "def _parse_document_info(self, info_str: str) -> tuple[str, str]:",
                ),
                (
                    "def _create_document_record(self, doc):",
                    "def _create_document_record(self, doc: Any) -> dict[str, Any]:",
                ),
                (
                    "def __exit__(self, exc_type, exc_val, exc_tb):",
                    "def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:",
                ),
            ],
        ),
        # document_delivery_schedule_service.py
        (
            "backend/apps/automation/services/document_delivery/document_delivery_schedule_service.py",
            [
                (
                    "def _create_schedule_task(self, schedule):",
                    "def _create_schedule_task(self, schedule: Any) -> None:",
                ),
            ],
        ),
    ]

    for file_path, replacements in fixes:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"文件不存在: {file_path}")
            continue

        content = path.read_text(encoding="utf-8")
        modified = False

        for old_str, new_str in replacements:
            if old_str in content:
                content = content.replace(old_str, new_str)
                modified = True
                logger.info(f"修复 {file_path}: {old_str[:50]}...")

        if modified:
            path.write_text(content, encoding="utf-8")
            logger.info(f"已修复文件: {file_path}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    logger.info("=" * 80)
    logger.info("开始修复 document_delivery 模块简单类型错误")
    logger.info("=" * 80)

    logger.info("\n1. 修复泛型类型参数缺失 (type-arg)")
    fix_type_arg_errors()

    logger.info("\n2. 修复函数缺少类型注解 (no-untyped-def)")
    fix_no_untyped_def_errors()

    logger.info("\n" + "=" * 80)
    logger.info("修复完成！")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
