"""兼容层：旧 workbench_service 路径转发到新目录。"""

from __future__ import annotations

from apps.enterprise_data.services.workbench.service import McpWorkbenchService

__all__ = ["McpWorkbenchService"]
