"""模拟庭审 WebSocket 消费者."""

from __future__ import annotations

import json
import logging
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class MockTrialConsumer(AsyncWebsocketConsumer):
    """模拟庭审 WebSocket 消费者."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.session_id: str | None = None
        self.user: Any | None = None
        self.session: Any | None = None
        # 庭审流程服务实例：对抗模式的运行态（AdversarialTrialService）挂在
        # flow 实例的 _adversarial_services 字典上，同一 WS 连接内必须复用
        # 同一实例——Channels 的 consumer 在整个连接生命周期复用，断开时实例
        # 随之回收；不同连接各一实例，无跨连接共享语义
        self.flow: Any | None = None

    def _get_flow(self) -> Any:
        """获取（首次创建并缓存）本连接的庭审流程服务实例.

        每条消息重建 flow 会把实例级运行态全部丢掉（对抗模式下用户介入
        会被静默跳过），因此必须走连接级单例.
        """
        if self.flow is None:
            from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService

            self.flow = MockTrialFlowService()
        return self.flow

    async def connect(self) -> None:  # pragma: no cover
        try:
            self.user = self.scope.get("user")
            if not self.user or isinstance(self.user, AnonymousUser):
                await self.close(code=4001)
                return

            self.session_id = self.scope["url_route"]["kwargs"].get("session_id")
            if not self.session_id:
                await self.close(code=4002)
                return

            self.session = await self._get_session(self.session_id)
            if not self.session:
                await self.close(code=4004)
                return

            await self.accept()
            await self.channel_layer.group_add(f"mock_trial_{self.session_id}", self.channel_name)

            from apps.litigation_ai.services.mock_trial.types import MockTrialContext, MockTrialStep

            flow = self._get_flow()
            ctx = MockTrialContext(
                session_id=self.session_id,
                case_id=self.session.case_id,
                user_id=self.user.id,
                current_step=MockTrialStep.INIT,
            )
            await flow.handle_init(ctx, self._send_message)
        except Exception as e:
            logger.error("MockTrial WebSocket 连接失败: %s", e, exc_info=True)
            await self.close(code=4000)

    async def disconnect(self, close_code: int) -> None:
        if self.session_id:
            try:
                await self.channel_layer.group_discard(f"mock_trial_{self.session_id}", self.channel_name)
            except Exception as e:
                logger.error("MockTrial WebSocket 断开失败: %s", e, exc_info=True)

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:  # pragma: no cover
        try:
            if not text_data:
                await self._send_error("消息内容为空")
                return

            message = json.loads(text_data)
            if not isinstance(message, dict):
                await self._send_error("消息必须是 JSON 对象")
                return

            msg_type = message.get("type")
            if not msg_type:
                await self._send_error("缺少消息类型")
                return

            handler = self._get_handler(msg_type)
            if not handler:
                await self._send_error(f"不支持的消息类型: {msg_type}")
                return

            await handler(message)
        except json.JSONDecodeError as e:
            await self._send_error(f"消息格式错误: {e}")
        except Exception as e:
            logger.error("MockTrial 处理消息失败: %s", e, exc_info=True)
            await self._send_error(e)

    def _get_handler(self, msg_type: str) -> Any:
        return {
            "user_message": self._handle_user_message,
            "select_mode": self._handle_select_mode,
            "skip_evidence": self._handle_skip_evidence,
            "end_debate": self._handle_end_debate,
            "set_difficulty": self._handle_set_difficulty,
        }.get(msg_type)

    async def _handle_user_message(self, message: dict[str, Any]) -> None:
        content = (message.get("content") or "").strip()
        if not content:
            await self._send_error("消息内容为空")
            return

        await self._add_message("user", content)

        from apps.litigation_ai.services.mock_trial.types import MockTrialContext, MockTrialStep

        flow = self._get_flow()
        step = await self._get_current_step(flow)
        assert self.session is not None and self.user is not None
        ctx = MockTrialContext(
            session_id=self.session_id or "",
            case_id=self.session.case_id,
            user_id=self.user.id,
            current_step=step,
        )

        if step == MockTrialStep.MODE_SELECT:
            await flow.handle_mode_select(ctx, content, self._send_message)
        elif step == MockTrialStep.MODEL_CONFIG:
            await flow.handle_model_config(ctx, content, self._send_message)
        elif step in (
            MockTrialStep.SIMULATION,
            MockTrialStep.FOCUS_ANALYSIS,
            MockTrialStep.COURT_OPENING,
            MockTrialStep.IDENTITY_CHECK,
            MockTrialStep.RIGHTS_NOTICE,
            MockTrialStep.APPEAL_STATEMENT,
            MockTrialStep.PLAINTIFF_STATEMENT,
            MockTrialStep.DEFENDANT_RESPONSE,
            MockTrialStep.COURT_INVESTIGATION,
            MockTrialStep.COURT_DEBATE,
            MockTrialStep.FINAL_STATEMENT,
            MockTrialStep.MEDIATION,
            MockTrialStep.COURT_SUMMARY,
        ):
            await flow.handle_simulation(ctx, content, self._send_message)
        elif step == MockTrialStep.SUMMARY:
            # SUMMARY 或其他步骤：提示用户
            await self._send_message(
                {
                    "type": "system_message",
                    "content": "当前会话已结束。如需继续，请新建会话。",
                }
            )

    async def _handle_select_mode(self, message: dict[str, Any]) -> None:
        mode = message.get("mode", "")
        if not mode:
            await self._send_error("缺少 mode 参数")
            return

        await self._add_message("user", f"选择模式：{mode}")

        from apps.litigation_ai.services.mock_trial.types import MockTrialContext, MockTrialStep

        flow = self._get_flow()
        assert self.session is not None and self.user is not None
        ctx = MockTrialContext(
            session_id=self.session_id or "",
            case_id=self.session.case_id,
            user_id=self.user.id,
            current_step=MockTrialStep.MODE_SELECT,
        )
        await flow.handle_mode_select(ctx, mode, self._send_message)

    async def _handle_skip_evidence(self, message: dict[str, Any]) -> None:
        """跳过剩余证据，直接生成质证总结."""
        await self._add_message("user", "跳过剩余证据")

        from apps.litigation_ai.services.mock_trial.types import MockTrialContext, MockTrialStep

        flow = self._get_flow()
        assert self.session is not None and self.user is not None
        ctx = MockTrialContext(
            session_id=self.session_id or "",
            case_id=self.session.case_id,
            user_id=self.user.id,
            current_step=MockTrialStep.SIMULATION,
        )
        await flow.handle_simulation(ctx, "跳过", self._send_message)

    async def _handle_end_debate(self, message: dict[str, Any]) -> None:
        """结束辩论."""
        await self._add_message("user", "结束辩论")

        from apps.litigation_ai.services.mock_trial.types import MockTrialContext, MockTrialStep

        flow = self._get_flow()
        assert self.session is not None and self.user is not None
        ctx = MockTrialContext(
            session_id=self.session_id or "",
            case_id=self.session.case_id,
            user_id=self.user.id,
            current_step=MockTrialStep.SIMULATION,
        )
        await flow.handle_simulation(ctx, "结束", self._send_message)

    async def _handle_set_difficulty(self, message: dict[str, Any]) -> None:
        """设置辩论难度."""
        difficulty = message.get("difficulty", "medium")
        if difficulty not in ("easy", "medium", "hard"):
            await self._send_error("无效的难度设置")
            return

        from apps.litigation_ai.services.flow.session_repository import LitigationSessionRepository

        repo = LitigationSessionRepository()
        await repo.update_metadata(self.session_id or "", {"debate_difficulty": difficulty})
        logger.info("辩论难度已设置为: %s", difficulty)

    # ---- Helpers ----

    async def _send_message(self, payload: dict[str, Any]) -> None:
        await self.send(text_data=json.dumps(payload, ensure_ascii=False))

    async def _send_progress(self, current: int, total: int, message: str = "") -> None:
        """发送进度更新."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "progress",
                    "current": current,
                    "total": total,
                    "percentage": int(current * 100 / total) if total > 0 else 0,
                    "message": message,
                },
                ensure_ascii=False,
            )
        )

    async def _send_error(self, error: Exception | str, code: str = "INVALID_REQUEST") -> None:
        if isinstance(error, Exception):
            from apps.core.exceptions.error_presentation import ExceptionPresenter

            presenter = ExceptionPresenter()
            envelope, _ = presenter.present(error, channel="ws", debug=getattr(settings, "DEBUG", False))
            payload = {
                "type": "error",
                "code": envelope.code,
                "message": envelope.message,
                "errors": envelope.errors,
                "retryable": envelope.retryable,
            }
            await self.send(text_data=json.dumps(payload, ensure_ascii=False))
            return
        await self.send(text_data=json.dumps({"type": "error", "message": error, "code": code}, ensure_ascii=False))

    @database_sync_to_async
    def _get_session(self, session_id: str) -> Any:
        """按 session_id 取模拟庭审会话，并校验归属（安全审计 IDOR）。

        与 litigation_consumer._get_session 同口径：非 superuser/is_admin
        只能访问自己的会话，否则任意已认证用户可连上他人会话读取案情并在
        他人会话上驱动 LLM 生成。user 缺失时同样 fail-closed（按 None 过滤）。
        """
        from apps.litigation_ai.models import LitigationSession

        qs = LitigationSession.objects.filter(session_id=session_id, session_type="mock_trial")
        user = getattr(self, "user", None)
        if user is None or not (getattr(user, "is_superuser", False) or getattr(user, "is_admin", False)):
            qs = qs.filter(user_id=getattr(user, "id", None))
        return qs.first()

    @database_sync_to_async
    def _add_message(self, role: str, content: str, metadata: dict[str, Any] | None = None) -> Any:
        from apps.litigation_ai.services import LitigationConversationService

        service = LitigationConversationService()
        return service.add_message(
            session_id=self.session_id or "", role=role, content=content, metadata=metadata or {}
        )

    @database_sync_to_async
    def _get_current_step(self, flow: Any) -> Any:
        return flow.get_current_step(self.session_id)
