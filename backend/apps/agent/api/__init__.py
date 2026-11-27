"""Agent app API 聚合路由。

按子域拆分模块，统一从本包导出 ``router``（apiSystem 单点挂载 ``/agent``）。
记忆子域单独注册在 ``/agent/memory``（见 ``memory_api.router``）。
"""

from __future__ import annotations

from ninja import Router

from .approval_api import router as approval_router
from .attachment_api import router as attachment_router
from .chat_api import router as chat_router
from .qoder_auth_api import router as qoder_auth_router
from .question_api import router as question_router
from .review_api import router as review_router
from .session_api import router as session_router
from .skill_api import router as skill_router
from .synthesis_api import router as synthesis_router
from .task_api import router as task_router
from .usage_api import router as usage_router

router = Router()

router.add_router("", session_router)
router.add_router("", chat_router)
router.add_router("", task_router)
router.add_router("", approval_router)
router.add_router("", question_router)
router.add_router("", review_router)
router.add_router("", synthesis_router)
router.add_router("", attachment_router)
router.add_router("", skill_router)
router.add_router("", usage_router)
router.add_router("", qoder_auth_router)
