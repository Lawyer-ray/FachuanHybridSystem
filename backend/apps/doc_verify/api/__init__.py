"""Ninja 路由（挂载前缀 /api/v1/doc-verify，见 apiSystem/apiSystem/api.py）。

三条 router 共用同一个前缀，路径互不重叠：
- `verify_api`  核对运行 / 裁决 / 待裁决清单
- `artifact_api` 出站基线冻结与清单
- `policy_api`  案件级策略（前端勾选框的落点）
"""

from .artifact_api import router as artifact_router
from .policy_api import router as policy_router
from .verify_api import router

__all__ = ["artifact_router", "policy_router", "router"]
