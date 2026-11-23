"""文档解析后台任务"""

from __future__ import annotations

import logging
from typing import Any

from apps.document_parsing.services.block_builder import block_to_dict

logger = logging.getLogger("apps.document_parsing")


def _serialize_block(block: Any) -> dict[str, Any]:
    """块 → 字典；非 ParsedBlock 的鸭子类型对象回退为尽可能保留可序列化字段。"""
    if isinstance(block, dict):
        return block
    try:
        return block_to_dict(block)
    except AttributeError:
        return {"type": str(getattr(block, "type", "unknown")), "text": str(getattr(block, "text", ""))}


def _coverage_dict(coverage: Any) -> dict[str, bool]:
    """能力位字典；缺字段时全 False（不声明即视为无能力）。"""
    as_dict = getattr(coverage, "as_dict", None)
    if callable(as_dict):
        return dict(as_dict())
    return {"has_blocks": False, "has_bbox": False, "has_confidence": False, "has_page_geometry": False}


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
    if isinstance(result, dict) and result.get("pending_callback"):
        # 回调等待中：任务留在 processing，由 webhook 端点写回终态。
        # 这里若继续走 mark_completed，会把空正文当成结果写进去。
        logger.info("document_parsing_hook: Task(id=%s) 已提交云端，等待回调", task_id)
        return

    if isinstance(result, dict) and result.get("success"):
        # backend_used：parse 结果用 parse_method，extract-text 结果用 method
        parsing_task.mark_completed(
            text=result.get("text", ""),
            markdown=result.get("markdown", ""),
            metadata=result.get("metadata", {}),
            backend_used=result.get("parse_method") or result.get("method") or "unknown",
            blocks=result.get("blocks") or [],
        )
        logger.info("document_parsing_hook: Task(id=%s) 已标记为完成", task_id)
    else:
        error_msg = result.get("error", "未知错误") if isinstance(result, dict) else str(result)
        parsing_task.mark_failed(error_msg)
        logger.info("document_parsing_hook: Task(id=%s) 已标记为失败: %s", task_id, error_msg)


def _callback_kwargs(record_id: int | None, backend: str, seed: str) -> dict[str, str]:
    """构建传给云后端的回调参数；不启用回调时返回空字典（走轮询）。

    auto 模式先解析出实际要用的云平台再判定，否则「auto 落到 mineru」时
    会误以为没配回调而白跑一次长轮询。
    """
    if record_id is None or not seed:
        return {}
    from apps.document_parsing.services.callback_config import webhook_url_for_record
    from apps.document_parsing.services.parser_factory import resolve_auto_backend

    provider = resolve_auto_backend() if backend in (None, "", "auto") else backend
    url = webhook_url_for_record(provider, record_id)
    if not url:
        return {}
    return {"callback_url": url, "callback_seed": seed}


def execute_parse_document(
    file_path: str,
    file_type: str,
    backend: str,
    extract_tables: bool,
    extract_images: bool,
    return_markdown: bool,
    callback_record_id: int | None = None,
    callback_seed: str = "",
) -> dict[str, Any]:
    """后台执行文档解析（由 Django-Q worker 调用）。

    Args:
        file_path: 已保存的文件绝对路径
        file_type: 文件扩展名（不含点号）
        backend: 解析后端（mineru / textin / local / auto）
        extract_tables: 是否提取表格
        extract_images: 是否提取图片
        return_markdown: 是否返回 Markdown
        callback_record_id: 解析记录 id；配置了回调时用于拼回调 URL
        callback_seed: 本任务的回调签名种子（来自记录，见调度服务）

    Returns:
        解析结果字典，Django-Q 会将其存入 Task.result。
        走回调时结果里的 ``pending_callback`` 非空，``success`` 为真但正文为空——
        此时任务记录刻意**不**标记完成（见 ``document_parsing_hook``），
        最终结果由回调写回。
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
            **_callback_kwargs(callback_record_id, backend, callback_seed),
        )

        pending = getattr(result, "pending_callback", None)
        if pending is not None:
            # G18（2026-11-23 二轮审计）：回调靠 `metadata['callback_job_id']` 找回任务，
            # 但 `bind_textin_job` 全仓零调用点 → 回调进来必 `task_not_found`，
            # 任务永久停在 processing（进程内 PendingCallback 注册表跨 worker 不生效）。
            # 这里补上落库绑定。
            if callback_record_id and str(pending.provider).lower() == "textin":
                from apps.document_parsing.services.callback_result_service import DocumentParsingCallbackResultService

                DocumentParsingCallbackResultService().bind_textin_job(int(callback_record_id), str(pending.job_id))
                logger.info("Textin 回调任务已绑定: record=%s job=%s", callback_record_id, pending.job_id)
            # 回调路径：worker 这里只负责把云端任务提交出去。不能回 success=True 的
            # 正常结果——hook 会把它当终态写成 completed（正文为空），回调再来就
            # 被幂等逻辑当成重复推送而丢弃。
            return {
                "success": True,
                "pending_callback": {"provider": pending.provider, "job_id": pending.job_id},
                "text": "",
                "markdown": "",
                "metadata": result.metadata or {},
                "parse_method": result.parse_method,
                "blocks": [],
                "coverage": _coverage_dict(None),
            }

        return {
            "success": True,
            "text": result.text,
            "markdown": result.markdown,
            "metadata": result.metadata or {},
            "parse_method": result.parse_method,
            # 块级结构是增强信息：后端未实现时缺字段不应让整次解析失败
            "blocks": [_serialize_block(b) for b in (getattr(result, "blocks", None) or [])],
            "coverage": _coverage_dict(getattr(result, "coverage", None)),
        }

    except Exception as exc:
        logger.exception("后台文档解析失败: %s", exc)
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
        logger.exception("后台文本提取失败: %s", exc)
        return {
            "success": False,
            "text": "",
            "error": str(exc),
        }
