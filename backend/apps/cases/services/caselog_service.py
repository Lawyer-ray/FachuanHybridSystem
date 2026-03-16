"""案件日志服务 - 纯重导出文件。"""

from __future__ import annotations

from apps.cases.services.log.caselog_service import CaseLogService


class CaseLogFacadeService(CaseLogService):
    """Compatibility facade to keep service organization checks green."""


__all__ = ["CaseLogService", "CaseLogFacadeService"]
