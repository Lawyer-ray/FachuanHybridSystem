"""客户导入 Schema。"""

from __future__ import annotations

from datetime import datetime

from ninja import Schema


class ClientImportSessionOut(Schema):
    """客户导入会话输出。"""

    id: int
    status: str
    phase: str
    discovered_count: int
    total_count: int
    success_count: int
    skip_count: int
    error_message: str
    progress_message: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
