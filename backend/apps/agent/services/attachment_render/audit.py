"""渲染审计日志。"""

from __future__ import annotations

import logging
from typing import Any

from .types import RenderResult

logger = logging.getLogger(__name__)


def log_render(
    *,
    who: Any,
    result: RenderResult,
    strategy: str = "",
    elapsed_ms: int = 0,
) -> None:
    """渲染审计：谁、读了哪个附件、读了几页、走什么策略、多大。

    用 ``extra`` 结构化输出（不拼字符串），日志系统可按字段聚合——
    「附件读不出来」是这类问题的唯一线索，必须能按 attachment_id 反查。
    """
    logger.info(
        "agent 附件渲染 attachment_id=%s who=%s pages=%s strategy=%s bytes=%s ok=%s error=%s elapsed_ms=%s",
        result.attachment_id,
        who,
        [p.page_no for p in result.pages],
        strategy or ",".join(sorted({str(p.strategy) for p in result.pages})),
        result.total_bytes,
        result.ok,
        result.error or "",
        elapsed_ms,
        extra={
            "who": who,
            "attachment_id": result.attachment_id,
            "pages": [p.page_no for p in result.pages],
            "strategy": strategy,
            "bytes": result.total_bytes,
            "ok": result.ok,
            "error": str(result.error or ""),
            "elapsed_ms": elapsed_ms,
        },
    )
