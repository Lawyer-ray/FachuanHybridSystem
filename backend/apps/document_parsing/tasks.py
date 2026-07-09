"""文档解析后台任务"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("apps.document_parsing")


def document_parsing_hook(task: Any) -> None:
    """Django-Q 完成钩子：将后台任务结果回写到 DocumentParsingTask 模型。

    Args:
        task: Django-Q Task 实例，包含 name、result、success 等字段。
              task.name 格式为 "document_parsing_{task_id}"。
    """
    from apps.document_parsing.models import DocumentParsingTask

    task_name = task.name or ""
    if not task_name.startswith("document_parsing_"):
        logger.warning("document_parsing_hook: 不认识的 task_name=%s", task_name)
        return

    try:
        task_id = int(task_name.split("_", 2)[2])
    except (ValueError, IndexError):
        logger.error("document_parsing_hook: 无法从 task_name=%s 解析 task_id", task_name)
        return

    try:
        parsing_task = DocumentParsingTask.objects.get(pk=task_id)
    except DocumentParsingTask.DoesNotExist:
        logger.error("document_parsing_hook: DocumentParsingTask(id=%s) 不存在", task_id)
        return

    result = task.result or {}
    if isinstance(result, dict) and result.get("success"):
        parsing_task.mark_completed(
            text=result.get("text", ""),
            markdown=result.get("markdown", ""),
            metadata=result.get("metadata", {}),
            backend_used=result.get("parse_method", "unknown"),
        )
        logger.info("document_parsing_hook: Task(id=%s) 已标记为完成", task_id)
    else:
        error_msg = result.get("error", "未知错误") if isinstance(result, dict) else str(result)
        parsing_task.mark_failed(error_msg)
        logger.info("document_parsing_hook: Task(id=%s) 已标记为失败: %s", task_id, error_msg)


def execute_parse_document(
    file_path: str,
    file_type: str,
    backend: str,
    extract_tables: bool,
    extract_images: bool,
    return_markdown: bool,
) -> dict[str, Any]:
    """后台执行文档解析（由 Django-Q worker 调用）。

    Args:
        file_path: 已保存的文件绝对路径
        file_type: 文件扩展名（不含点号）
        backend: 解析后端（mineru / local / paddleocr / auto）
        extract_tables: 是否提取表格
        extract_images: 是否提取图片
        return_markdown: 是否返回 Markdown

    Returns:
        解析结果字典，Django-Q 会将其存入 Task.result
    """
    from apps.document_parsing.services import get_document_parser

    logger.info("后台开始解析文档: path=%s, backend=%s", file_path, backend)

    try:
        parser = get_document_parser(backend=backend)
        result = parser.parse_document(
            file_path=file_path,
            file_type=file_type,
            extract_tables=extract_tables,
            extract_images=extract_images,
            return_markdown=return_markdown,
        )

        return {
            "success": True,
            "text": result.text,
            "markdown": result.markdown,
            "metadata": result.metadata or {},
            "parse_method": result.parse_method,
        }

    except Exception as exc:
        logger.error("后台文档解析失败: %s", exc, exc_info=True)
        return {
            "success": False,
            "error": str(exc),
        }


def execute_extract_text(
    file_path: str,
    backend: str,
    max_length: int | None,
) -> dict[str, Any]:
    """后台执行文本提取（由 Django-Q worker 调用）。

    Args:
        file_path: 已保存的文件绝对路径
        backend: 解析后端
        max_length: 最大文本长度

    Returns:
        提取结果字典，Django-Q 会将其存入 Task.result
    """
    from apps.document_parsing.services import get_document_parser

    logger.info("后台开始提取文本: path=%s, backend=%s", file_path, backend)

    try:
        parser = get_document_parser(backend=backend)
        result = parser.extract_text(
            file_path=file_path,
            max_length=max_length,
        )

        return {
            "success": result.success,
            "text": result.text,
            "method": result.method,
            "metadata": result.metadata or {},
        }

    except Exception as exc:
        logger.error("后台文本提取失败: %s", exc, exc_info=True)
        return {
            "success": False,
            "text": "",
            "error": str(exc),
        }
