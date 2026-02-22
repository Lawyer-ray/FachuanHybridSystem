"""
案件 Admin 服务 - 纯重导出文件

所有实现已迁移到 services/case/case_admin_service.py.
本文件仅做重导出,保持向后兼容性.
"""

from __future__ import annotations

from apps.cases.services.case.case_admin_service import CaseAdminService

__all__ = ["CaseAdminService"]
