"""
案件群聊服务

本模块实现案件群聊的业务逻辑,包括群聊创建、管理和消息推送功能.
采用服务层模式,协调群聊提供者工厂和数据持久化操作.

设计原则:
- 单一职责:专注于案件群聊业务逻辑
- 依赖注入:通过工厂模式获取群聊提供者
- 事务一致性:确保群聊创建和数据库操作的一致性
- 错误处理:统一的异常处理和日志记录

主要功能:
- 为案件创建群聊
- 自动生成群聊名称
- 发送文书通知到群聊
- 管理群聊绑定关系
- 支持多平台群聊
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from apps.cases.exceptions import ChatCreationException, MessageSendException
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.core.enums import ChatPlatform
from apps.core.exceptions import ValidationException
from apps.core.security import AccessContext

from .naming import ChatNameBuilder
from .notification_usecase import SendNotificationUsecase
from .provider_facade import ChatProviderFacade
from .recreate_policy import ChatRecreatePolicy
from .repo import CaseChatRepository

logger = logging.getLogger(__name__)


class CaseChatService:

    def __init__(
        self,
        *,
        repo: CaseChatRepository | None = None,
        name_builder: ChatNameBuilder | None = None,
        provider_facade: ChatProviderFacade | None = None,
        recreate_policy: ChatRecreatePolicy | None = None,
        access_policy: CaseAccessPolicy | None = None,
    ) -> None:
        self.repo = repo or CaseChatRepository()
        self.name_builder = name_builder or ChatNameBuilder()
        self.provider_facade = provider_facade or ChatProviderFacade()
        self.recreate_policy = recreate_policy or ChatRecreatePolicy()
        self._access_policy = access_policy
        self._send_notification_usecase = None

    @property
    def access_policy(self) -> CaseAccessPolicy:
        if self._access_policy is None:
            self._access_policy = CaseAccessPolicy()
        return self._access_policy

    def _resolve_access(
        self, *, user, org_access, perm_open_access: bool, ctx: AccessContext | None
    ) -> tuple[Any, ...]:
        if ctx is not None:
            return (ctx.user, ctx.org_access, ctx.perm_open_access)
        return (user, org_access, perm_open_access)

    def _require_case_access(
        self, case: Any, *, user, org_access, perm_open_access: bool, ctx: AccessContext | None
    ) -> None:
        user, org_access, perm_open_access = self._resolve_access(
            user=user, org_access=org_access, perm_open_access=perm_open_access, ctx=ctx
        )
        self.access_policy.ensure_access(
            case_id=case.id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            case=case,
            message="无权限访问此案件",
        )

    def _resolve_owner_id(self) -> Any:
        from apps.core.config import get_config

        return get_config("features.case_chat.default_owner_id", None)

    def create_chat_for_case(
        self,
        case_id: int,
        platform: ChatPlatform = ChatPlatform.FEISHU,
        owner_id: str | None = None,
        user: Any = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        ctx: AccessContext | None = None,
    ) -> Any:
        """为案件创建群聊

        通过群聊提供者工厂获取对应平台的提供者,创建群聊并保存记录.
        使用数据库事务确保群聊创建和数据持久化的一致性.

        Args:
            case_id: 案件ID
            platform: 群聊平台,默认为飞书
            owner_id: 群主ID(可选,某些平台需要)

        Returns:
            CaseChat: 创建的群聊记录

        Raises:
            NotFoundError: 当案件不存在时
            ChatCreationException: 当群聊创建失败时
            ValidationException: 当参数无效时

        Requirements: 4.1, 4.2, 4.5

        Example:
            service = CaseChatService()
            chat = service.create_chat_for_case(
                case_id=123,
                platform=ChatPlatform.FEISHU
            )
            print(f"创建群聊成功: {chat.name}")
        """
        logger.info(f"开始为案件创建群聊: case_id={case_id}, platform={platform.value}")
        case = self.repo.get_case(case_id=case_id)
        self._require_case_access(case, user=user, org_access=org_access, perm_open_access=perm_open_access, ctx=ctx)
        chat_name = self.name_builder.build(case=case)
        owner_id = owner_id or self._resolve_owner_id()
        provider = self.provider_facade.get_provider_for_creation(platform=platform)
        try:
            result = self.provider_facade.create_chat(provider=provider, chat_name=chat_name, owner_id=owner_id)
            if not result.success:
                raise ChatCreationException(
                    message=result.message or "群聊创建失败",
                    code="CHAT_CREATION_FAILED",
                    platform=platform.value,
                    error_code=result.error_code,
                    errors={"provider_response": result.raw_response, "chat_name": chat_name},
                )
            case_chat = self.repo.create_binding(
                case=case, platform=platform, chat_id=result.chat_id, name=result.chat_name or chat_name, is_active=True
            )
            logger.info(
                f"群聊创建成功: case_id={case_id}, chat_id={result.chat_id}, platform={platform.value}, name={case_chat.name}"
            )
            return case_chat
        except ChatCreationException:
            raise
        except Exception as e:
            raise ChatCreationException(
                message="创建群聊时发生系统错误",
                code="SYSTEM_ERROR",
                platform=platform.value,
                errors={"case_id": case_id, "original_error": str(e)},
            ) from e

    def get_or_create_chat(
        self,
        case_id: int,
        platform: ChatPlatform = ChatPlatform.FEISHU,
        owner_id: str | None = None,
        user: Any = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        ctx: AccessContext | None = None,
    ) -> None:
        """获取或创建案件群聊

        检查指定案件和平台是否已存在活跃的群聊记录.
        如果存在则直接返回,不存在则自动创建新的群聊.

        Args:
            case_id: 案件ID
            platform: 群聊平台,默认为飞书
            owner_id: 群主ID(仅在创建时使用)

        Returns:
            CaseChat: 现有或新创建的群聊记录

        Raises:
            NotFoundError: 当案件不存在时
            ChatCreationException: 当群聊创建失败时
            ValidationException: 当参数无效时

        Requirements: 6.1, 6.2

        Example:
            service = CaseChatService()
            # 第一次调用会创建群聊
            chat1 = service.get_or_create_chat(case_id=123)
            # 第二次调用会返回相同的群聊
            chat2 = service.get_or_create_chat(case_id=123)
            assert chat1.id == chat2.id
        """
        logger.debug(f"获取或创建群聊: case_id={case_id}, platform={platform.value}")
        case = self.repo.get_case(case_id=case_id)
        self._require_case_access(case, user=user, org_access=org_access, perm_open_access=perm_open_access, ctx=ctx)
        existing_chat = self.repo.get_active_chat(case_id=case_id, platform=platform)
        if existing_chat:
            logger.debug(f"找到现有群聊: chat_id={existing_chat.chat_id}, name={existing_chat.name}")
            return existing_chat
        logger.info(f"未找到现有群聊,开始创建新群聊: case_id={case_id}, platform={platform.value}")
        return self.create_chat_for_case(
            case_id, platform, owner_id, user=user, org_access=org_access, perm_open_access=perm_open_access, ctx=ctx
        )

    def send_document_notification(
        self,
        case_id: int,
        sms_content: str,
        document_paths: list[Any] | None = None,
        platform: ChatPlatform = ChatPlatform.FEISHU,
        title: str = "📋 法院文书通知",
        user: Any = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        ctx: AccessContext | None = None,
    ) -> Any:
        """发送文书通知到群聊

        获取或创建指定案件的群聊,然后发送文书通知消息.
        支持同时发送文本消息和多个文件附件.

        Args:
            case_id: 案件ID
            sms_content: 短信内容(作为消息正文)
            document_paths: 文书文件路径列表(可选)
            platform: 群聊平台,默认为飞书
            title: 消息标题,默认为"📋 法院文书通知"

        Returns:
            ChatResult: 消息发送结果

        Raises:
            NotFoundError: 当案件不存在时
            MessageSendException: 当消息发送失败时
            ChatCreationException: 当群聊创建失败时
            ValidationException: 当参数无效时

        Requirements: 6.3, 8.1, 8.2

        Example:
            service = CaseChatService()
            result = service.send_document_notification(
                case_id=123,
                sms_content="您有新的法院文书,请及时查看.",
                document_paths=["/path/to/document1.pd", "/path/to/document2.pdf"]
            )
            if result.success:
                print("通知发送成功")
        """
        logger.info(
            f"发送文书通知: case_id={case_id}, platform={platform.value}, file_count={(len(document_paths) if document_paths else 0)}"
        )
        if not sms_content or not sms_content.strip():
            raise ValidationException(
                message="短信内容不能为空", code="INVALID_SMS_CONTENT", errors={"sms_content": "短信内容为必填项"}
            )
        case = self.repo.get_case(case_id=case_id)
        self._require_case_access(case, user=user, org_access=org_access, perm_open_access=perm_open_access, ctx=ctx)
        chat = None
        try:
            chat = self.get_or_create_chat(
                case_id, platform, user=user, org_access=org_access, perm_open_access=perm_open_access, ctx=ctx
            )
            from apps.cases.dependencies import create_message_content

            content = create_message_content(title=title, text=sms_content.strip(), file_path=None)
            usecase = self._get_send_notification_usecase()
            result = usecase.execute(
                case_id=case_id, platform=platform, chat=chat, content=content, document_paths=document_paths
            )
            logger.info(f"文书通知发送完成: case_id={case_id}, chat_id={chat.chat_id}, success={result.success}")
            return result
        except MessageSendException:
            raise
        except Exception as e:
            raise MessageSendException(
                message="发送文书通知时发生系统错误",
                code="SYSTEM_ERROR",
                platform=platform.value,
                chat_id=getattr(chat, "chat_id", "") if chat else "",
                errors={"case_id": case_id, "original_error": str(e)},
            ) from e

    def _get_send_notification_usecase(self) -> SendNotificationUsecase:
        if self._send_notification_usecase is None:
            self._send_notification_usecase = SendNotificationUsecase(
                repo=self.repo,
                provider_facade=self.provider_facade,
                recreate_policy=self.recreate_policy,
                chat_creator=lambda case_id, platform: self.create_chat_for_case(case_id, platform),
            )
        return self._send_notification_usecase

    def unbind_chat(self, chat_id: int) -> bool:
        """解除群聊绑定(软删除)

        将指定的群聊记录标记为非活跃状态,但不删除数据库记录.
        这样可以保留历史记录,同时使群聊不再参与业务逻辑.

        Args:
            chat_id: 群聊记录ID(不是平台的chat_id)

        Returns:
            bool: 是否成功解除绑定

        Raises:
            ValidationException: 当chat_id无效时

        Requirements: 5.2

        Example:
            service = CaseChatService()
            success = service.unbind_chat(chat_id=456)
            if success:
                print("群聊绑定已解除")
        """
        try:
            return self.repo.unbind_chat(chat_id=chat_id)
        except ValidationException:
            raise
        except Exception as e:
            raise ValidationException(
                message="解除群聊绑定时发生系统错误",
                code="SYSTEM_ERROR",
                errors={"chat_id": chat_id, "original_error": str(e)},
            ) from e

    def bind_existing_chat(
        self,
        case_id: int,
        platform: ChatPlatform,
        chat_id: str,
        chat_name: str | None = None,
        user: Any = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        ctx: AccessContext | None = None,
    ) -> None:
        """手动绑定已存在的群聊

        将已存在的群聊(通过chat_id标识)绑定到指定案件.
        适用于手动管理群聊绑定关系的场景.

        Args:
            case_id: 案件ID
            platform: 群聊平台
            chat_id: 平台群聊ID
            chat_name: 群聊名称(可选,如果不提供会尝试从平台获取)

        Returns:
            CaseChat: 创建的群聊绑定记录

        Raises:
            NotFoundError: 当案件不存在时
            ValidationException: 当参数无效或群聊已绑定时
            ChatCreationException: 当无法获取群聊信息时

        Requirements: 5.3

        Example:
            service = CaseChatService()
            chat = service.bind_existing_chat(
                case_id=123,
                platform=ChatPlatform.FEISHU,
                chat_id="oc_abc123def456",
                chat_name="【一审】张三诉李四合同纠纷案"
            )
        """
        logger.info(f"绑定已存在的群聊: case_id={case_id}, platform={platform.value}, chat_id={chat_id}")
        if not chat_id or not chat_id.strip():
            raise ValidationException(
                message="群聊ID不能为空", code="INVALID_CHAT_ID", errors={"chat_id": "群聊ID为必填项"}
            )
        chat_id = chat_id.strip()
        case = self.repo.get_case(case_id=case_id)
        self._require_case_access(case, user=user, org_access=org_access, perm_open_access=perm_open_access, ctx=ctx)
        self.repo.ensure_not_bound(case_id=case_id, platform=platform, chat_id=chat_id)
        if not chat_name:
            chat_name = self.provider_facade.try_get_chat_name(platform=platform, chat_id=chat_id)
        if not chat_name:
            chat_name = self.name_builder.build(case=case)
        try:
            case_chat = self.repo.create_binding(
                case=case, platform=platform, chat_id=chat_id, name=chat_name, is_active=True
            )
            logger.info(
                f"群聊绑定成功: case_id={case_id}, chat_id={chat_id}, platform={platform.value}, name={chat_name}"
            )
            return case_chat
        except ValidationException:
            raise
        except Exception as e:
            raise ValidationException(
                message="创建群聊绑定记录失败",
                code="BINDING_CREATION_ERROR",
                errors={"case_id": case_id, "chat_id": chat_id, "original_error": str(e)},
            ) from e
