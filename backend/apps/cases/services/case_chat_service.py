"""
案件群聊服务

本模块实现案件群聊的业务逻辑，包括群聊创建、管理和消息推送功能。
采用服务层模式，协调群聊提供者工厂和数据持久化操作。

设计原则：
- 单一职责：专注于案件群聊业务逻辑
- 依赖注入：通过工厂模式获取群聊提供者
- 事务一致性：确保群聊创建和数据库操作的一致性
- 错误处理：统一的异常处理和日志记录

主要功能：
- 为案件创建群聊
- 自动生成群聊名称
- 发送文书通知到群聊
- 管理群聊绑定关系
- 支持多平台群聊
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

if TYPE_CHECKING:
    from apps.core.dto.chat import ChatResult

from apps.cases.exceptions import ChatCreationException, MessageSendException
from apps.cases.models import Case, CaseChat
from apps.core.dto.chat import MessageContent
from apps.core.enums import ChatPlatform
from apps.core.exceptions import NotFoundError, ValidationException

logger = logging.getLogger(__name__)


class CaseChatService:
    """案件群聊服务

    负责案件群聊的创建、管理和消息推送业务逻辑。
    通过 ChatProviderFactory 获取具体的群聊提供者实现。

    主要职责：
    - 群聊生命周期管理（创建、绑定、解绑）
    - 群聊名称生成和格式化
    - 消息和文件推送
    - 数据持久化和事务管理
    """

    def __init__(self) -> None:
        """初始化案件群聊服务"""
        logger.debug("CaseChatService 初始化完成")

    @property
    def factory(self) -> Any:
        """懒加载群聊提供者工厂"""
        from apps.core.interfaces import ServiceLocator

        return ServiceLocator.get_chat_provider_factory()

    def _build_message_content(self, title: str, text: str) -> MessageContent:
        """构造 MessageContent 对象"""
        return MessageContent(title=title, text=text, file_path=None)

    def _build_chat_name(self, case: Case) -> str:
        """构建群聊名称

        使用 ChatNameConfigService 根据配置的模板生成群聊名称。
        支持自定义模板、默认阶段显示和长度限制。

        Args:
            case: 案件对象

        Returns:
            str: 格式化的群聊名称

        Requirements: 1.2, 2.2, 3.2, 5.2

        Examples:
            case.current_stage = "FIRST_TRIAL", case.name = "张三诉李四合同纠纷案"
            -> "【一审】张三诉李四合同纠纷案"

            case.current_stage = None, case.name = "王五诉赵六债务纠纷案"
            -> "【待定】王五诉赵六债务纠纷案"
        """
        if not case:
            raise ValidationException(
                message="案件对象不能为空", code="INVALID_CASE", errors={"case": "案件对象为必填项"}
            )

        if not case.name:
            raise ValidationException(
                message="案件名称不能为空", code="INVALID_CASE_NAME", errors={"case_name": "案件名称为必填项"}
            )

        # 使用配置服务渲染群名
        from apps.cases.services.chat_name_config_service import ChatNameConfigService

        config_service = ChatNameConfigService()

        # 获取阶段显示名称
        stage_display = None
        if case.current_stage:
            try:
                stage_display = case.get_current_stage_display()
            except (AttributeError, ValueError):
                # 如果获取显示名称失败，使用原始值
                stage_display = case.current_stage
                logger.warning(f"无法获取案件阶段显示名称: {case.current_stage}, 使用原始值")

        # 获取案件类型显示名称
        case_type_display = None
        if hasattr(case, "case_type") and case.case_type:
            try:
                case_type_display = case.get_case_type_display()
            except (AttributeError, ValueError):
                case_type_display = case.case_type
                logger.warning(f"无法获取案件类型显示名称: {case.case_type}, 使用原始值")

        # 使用配置服务渲染群名（包含模板替换和长度截断）
        chat_name = config_service.render_chat_name(
            case_name=case.name, stage=stage_display, case_type=case_type_display
        )

        logger.debug(f"生成群聊名称: {chat_name} (案件ID: {case.id})")
        return chat_name

    def _get_case(self, case_id: int) -> Case:
        """获取案件对象

        根据案件ID获取案件对象，包含必要的验证。

        Args:
            case_id: 案件ID

        Returns:
            Case: 案件对象

        Raises:
            NotFoundError: 当案件不存在时
            ValidationException: 当案件ID无效时

        Requirements: 4.3, 4.4
        """
        if not case_id or not isinstance(case_id, int) or case_id <= 0:
            raise ValidationException(
                message="无效的案件ID", code="INVALID_CASE_ID", errors={"case_id": "案件ID必须是正整数"}
            )

        try:
            case = Case.objects.get(id=case_id)
            logger.debug(f"获取案件成功: ID={case_id}, 名称={case.name}")
            return case
        except ObjectDoesNotExist as e:
            logger.error(f"案件不存在: ID={case_id}")
            raise NotFoundError(
                message=f"案件不存在: ID={case_id}", code="CASE_NOT_FOUND", errors={"case_id": case_id}
            ) from e

    def _resolve_owner_id(self, owner_id: str | None) -> str | None:
        """解析群主 ID，未指定时从配置读取默认值"""
        if owner_id:
            return owner_id
        from django.conf import settings

        try:
            if getattr(settings, "CONFIG_MANAGER_AVAILABLE", False):
                get_unified_config = getattr(settings, "get_unified_config", None)
                if get_unified_config:
                    default_owner = get_unified_config("features.case_chat.default_owner_id")
                    if default_owner:
                        logger.debug(f"使用默认群主（统一配置）: {default_owner}")
                        return str(default_owner)
        except Exception as e:
            logger.debug(f"从统一配置获取默认群主失败: {e}")

        default_owner = getattr(settings, "CASE_CHAT", {}).get("DEFAULT_OWNER_ID")
        if default_owner:
            logger.debug(f"使用默认群主: {default_owner}")
            return str(default_owner)
        return None

    def _get_available_provider(self, platform: ChatPlatform) -> Any:
        """获取可用的群聊提供者，不可用时抛出异常"""
        try:
            provider = self.factory.get_provider(platform)
        except Exception as e:
            logger.error(f"获取群聊提供者失败: platform={platform.value}, error={e!s}")
            raise ChatCreationException(
                message=f"无法获取群聊提供者: {platform.label}",
                code="PROVIDER_UNAVAILABLE",
                platform=platform.value,
                errors={"original_error": str(e)},
            ) from e
        if not provider.is_available():
            logger.error(f"群聊提供者不可用: platform={platform.value}")
            raise ChatCreationException(
                message=f"群聊平台不可用: {platform.label}",
                code="PROVIDER_NOT_AVAILABLE",
                platform=platform.value,
                errors={"platform_status": "配置不完整或服务不可用"},
            )
        return provider

    def _create_chat_in_transaction(
        self, case: Any, platform: ChatPlatform, chat_name: str, owner_id: str | None
    ) -> "CaseChat":
        """在事务中调用提供者创建群聊并保存记录"""
        provider = self._get_available_provider(platform)
        try:
            with transaction.atomic():
                result = provider.create_chat(chat_name, owner_id)
                if not result.success:
                    logger.error(f"群聊创建失败: {result.message}, error_code={result.error_code}")
                    raise ChatCreationException(
                        message=result.message or "群聊创建失败",
                        code="CHAT_CREATION_FAILED",
                        platform=platform.value,
                        error_code=result.error_code,
                        errors={"provider_response": result.raw_response, "chat_name": chat_name},
                    )
                case_chat = CaseChat.objects.create(
                    case=case,
                    platform=platform,
                    chat_id=result.chat_id or "",
                    name=result.chat_name or chat_name,
                    is_active=True,
                )
                logger.info(
                    f"群聊创建成功: case_id={case.pk}, chat_id={result.chat_id},"
                    f" platform={platform.value}, name={case_chat.name}"
                )
                return case_chat
        except ChatCreationException:
            raise
        except Exception as e:
            logger.error(f"创建群聊时发生未预期错误: case_id={case.pk}, error={e!s}")
            raise ChatCreationException(
                message="创建群聊时发生系统错误",
                code="SYSTEM_ERROR",
                platform=platform.value,
                errors={"case_id": case.pk, "original_error": str(e)},
            ) from e

    def create_chat_for_case(
        self, case_id: int, platform: ChatPlatform = ChatPlatform.FEISHU, owner_id: str | None = None
    ) -> "CaseChat":
        """为案件创建群聊"""
        logger.info(f"开始为案件创建群聊: case_id={case_id}, platform={platform.value}")
        case = self._get_case(case_id)
        chat_name = self._build_chat_name(case)
        resolved_owner = self._resolve_owner_id(owner_id)
        return self._create_chat_in_transaction(case, platform, chat_name, resolved_owner)

    def get_or_create_chat(
        self, case_id: int, platform: ChatPlatform = ChatPlatform.FEISHU, owner_id: str | None = None
    ) -> CaseChat:
        """获取或创建案件群聊

        检查指定案件和平台是否已存在活跃的群聊记录。
        如果存在则直接返回，不存在则自动创建新的群聊。

        Args:
            case_id: 案件ID
            platform: 群聊平台，默认为飞书
            owner_id: 群主ID（仅在创建时使用）

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

        # 验证案件存在性（这也会验证 case_id 的有效性）
        self._get_case(case_id)

        # 查找现有的活跃群聊
        existing_chat = CaseChat.objects.filter(case_id=case_id, platform=platform, is_active=True).first()

        if existing_chat:
            logger.debug(f"找到现有群聊: chat_id={existing_chat.chat_id}, name={existing_chat.name}")
            return cast(CaseChat, existing_chat)

        # 不存在则创建新群聊
        logger.info(f"未找到现有群聊，开始创建新群聊: case_id={case_id}, platform={platform.value}")
        return self.create_chat_for_case(case_id, platform, owner_id)

    def _send_files_to_chat(self, provider: Any, chat: Any, document_paths: list[Any]) -> str:
        """逐个发送文件到群聊，返回结果描述"""
        total = len(document_paths)
        ok = 0
        for i, file_path in enumerate(document_paths, 1):
            try:
                r = provider.send_file(chat.chat_id, file_path)
                if r.success:
                    ok += 1
                    logger.info(f"文件发送成功 ({i}/{total}): {file_path}")
                else:
                    logger.warning(f"文件发送失败 ({i}/{total}): {file_path}, 错误: {r.message}")
            except Exception as e:
                logger.error(f"文件发送异常 ({i}/{total}): {file_path}, 错误: {e!s}")
        if ok == total:
            return f"消息和所有文件发送成功 ({ok} 个文件)"
        if ok > 0:
            return f"消息发送成功，部分文件发送成功 ({ok}/{total} 个文件)"
        return f"消息发送成功，但所有文件发送失败 ({total - ok} 个文件)"

    def _retry_send_after_chat_recreate(
        self, provider: Any, chat: Any, content: Any, case_id: int, platform: "ChatPlatform", result: Any
    ) -> tuple[Any, Any]:
        """群聊解散时重建群聊并重试发送，返回 (new_result, new_chat)"""
        logger.warning(f"群聊可能已解散，尝试创建新群聊: chat_id={chat.chat_id}")
        chat.is_active = False
        chat.save()
        try:
            new_chat = self.create_chat_for_case(case_id, platform)
            logger.info(f"创建新群聊成功，重试发送消息: old={chat.chat_id}, new={new_chat.chat_id}")
            new_result = provider.send_message(new_chat.chat_id, content)
            if new_result.success:
                logger.info(f"重试发送消息成功: new_chat_id={new_chat.chat_id}")
            else:
                logger.error(f"重试发送消息仍然失败: new_chat_id={new_chat.chat_id}")
            return new_result, new_chat
        except Exception as retry_error:
            logger.error(f"创建新群聊或重试发送失败: {retry_error!s}")
            raise MessageSendException(
                message=f"群聊已解散，重新创建群聊失败: {retry_error!s}",
                code="CHAT_RECREATE_FAILED",
                platform=platform.value,
                chat_id=chat.chat_id,
                error_code=result.error_code,
                errors={
                    "original_error": result.message,
                    "retry_error": str(retry_error),
                    "provider_response": result.raw_response,
                },
            ) from retry_error

    def send_document_notification(
        self,
        case_id: int,
        sms_content: str,
        document_paths: list[Any] | None = None,
        platform: ChatPlatform = ChatPlatform.FEISHU,
        title: str = "📋 法院文书通知",
    ) -> ChatResult:
        """发送文书通知到群聊"""
        logger.info(
            f"发送文书通知: case_id={case_id}, platform={platform.value},"
            f" file_count={len(document_paths) if document_paths else 0}"
        )

        if not sms_content or not sms_content.strip():
            raise ValidationException(
                message="短信内容不能为空",
                code="INVALID_SMS_CONTENT",
                errors={"sms_content": "短信内容为必填项"},
            )

        chat = self.get_or_create_chat(case_id, platform)

        try:
            provider = self.factory.get_provider(platform)
        except Exception as e:
            logger.error(f"获取群聊提供者失败: platform={platform.value}, error={e!s}")
            raise MessageSendException(
                message=f"无法获取群聊提供者: {platform.label}",
                code="PROVIDER_UNAVAILABLE",
                platform=platform.value,
                chat_id=chat.chat_id,
                errors={"original_error": str(e)},
            ) from e

        content = self._build_message_content(title=title, text=sms_content.strip())

        try:
            result = provider.send_message(chat.chat_id, content)

            if not result.success:
                logger.error(
                    f"消息发送失败: chat_id={chat.chat_id}, message={result.message}, error_code={result.error_code}"
                )
                if self._is_chat_not_found_error(result):
                    result, chat = self._retry_send_after_chat_recreate(
                        provider, chat, content, case_id, platform, result
                    )

            if not result.success:
                raise MessageSendException(
                    message=result.message or "消息发送失败",
                    code="MESSAGE_SEND_FAILED",
                    platform=platform.value,
                    chat_id=chat.chat_id,
                    error_code=result.error_code,
                    errors={"provider_response": result.raw_response, "content_title": title},
                )

            if document_paths and result.success:
                logger.info(f"开始发送 {len(document_paths)} 个文件到群聊: chat_id={chat.chat_id}")
                result.message = self._send_files_to_chat(provider, chat, document_paths)

            logger.info(f"文书通知发送完成: case_id={case_id}, chat_id={chat.chat_id}, success={result.success}")
            return result

        except MessageSendException:
            raise
        except Exception as e:
            logger.error(f"发送文书通知时发生未预期错误: case_id={case_id}, chat_id={chat.chat_id}, error={e!s}")
            raise MessageSendException(
                message="发送文书通知时发生系统错误",
                code="SYSTEM_ERROR",
                platform=platform.value,
                chat_id=chat.chat_id,
                errors={"case_id": case_id, "original_error": str(e)},
            ) from e

    def _is_chat_not_found_error(self, result: ChatResult) -> bool:
        """检查是否是群聊不存在的错误

        根据不同平台的错误代码判断群聊是否已解散或不存在。

        Args:
            result: 消息发送结果

        Returns:
            bool: 是否是群聊不存在的错误
        """
        if not result.error_code:
            return False

        # 飞书平台的群聊不存在错误代码
        feishu_chat_not_found_codes = [
            "230002",  # 群聊不存在
            "230003",  # 群聊已解散
            "230004",  # 机器人不在群聊中
            "99991663",  # 群聊不存在或机器人不在群聊中
            "99991664",  # 群聊已解散
        ]

        # 检查错误代码
        error_code = str(result.error_code)
        if error_code in feishu_chat_not_found_codes:
            return True

        # 检查错误消息中的关键词
        error_message = result.message or ""
        chat_not_found_keywords = [
            "群聊不存在",
            "群聊已解散",
            "chat not found",
            "chat dissolved",
            "bot not in chat",
            "机器人不在群聊中",
        ]

        for keyword in chat_not_found_keywords:
            if keyword.lower() in error_message.lower():
                return True

        return False

    def unbind_chat(self, chat_id: int) -> bool:
        """解除群聊绑定（软删除）

        将指定的群聊记录标记为非活跃状态，但不删除数据库记录。
        这样可以保留历史记录，同时使群聊不再参与业务逻辑。

        Args:
            chat_id: 群聊记录ID（不是平台的chat_id）

        Returns:
            bool: 是否成功解除绑定

        Raises:
            ValidationException: 当chat_id无效时

        Requirements: 5.2

        Example:
            service = CaseChatService()
            success = service.unbind_chat(chat_id=456)
            if success:
                logger.info("群聊绑定已解除")
        """
        logger.info(f"解除群聊绑定: chat_id={chat_id}")
        if not chat_id or not isinstance(chat_id, int) or chat_id <= 0:
            raise ValidationException(
                message="无效的群聊ID", code="INVALID_CHAT_ID", errors={"chat_id": "群聊ID必须是正整数"}
            )

        try:
            # 使用软删除：将 is_active 设置为 False
            updated_count = CaseChat.objects.filter(id=chat_id, is_active=True).update(  # 只更新当前活跃的记录
                is_active=False
            )

            success = updated_count > 0

            if success:
                logger.info(f"群聊绑定解除成功: chat_id={chat_id}")
            else:
                logger.warning(f"群聊绑定解除失败，记录不存在或已解除: chat_id={chat_id}")

            return success

        except Exception as e:
            logger.error(f"解除群聊绑定时发生错误: chat_id={chat_id}, error={e!s}")
            raise ValidationException(
                message="解除群聊绑定时发生系统错误",
                code="SYSTEM_ERROR",
                errors={"chat_id": chat_id, "original_error": str(e)},
            ) from e

    def bind_existing_chat(
        self, case_id: int, platform: ChatPlatform, chat_id: str, chat_name: str | None = None
    ) -> CaseChat:
        """手动绑定已存在的群聊

        将已存在的群聊（通过chat_id标识）绑定到指定案件。
        适用于手动管理群聊绑定关系的场景。

        Args:
            case_id: 案件ID
            platform: 群聊平台
            chat_id: 平台群聊ID
            chat_name: 群聊名称（可选，如果不提供会尝试从平台获取）

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

        # 验证参数
        if not chat_id or not chat_id.strip():
            raise ValidationException(
                message="群聊ID不能为空", code="INVALID_CHAT_ID", errors={"chat_id": "群聊ID为必填项"}
            )

        chat_id = chat_id.strip()

        # 获取案件对象（这也会验证案件存在性）
        case = self._get_case(case_id)

        # 检查是否已存在相同的绑定
        existing_binding = CaseChat.objects.filter(
            case_id=case_id, platform=platform, chat_id=chat_id, is_active=True
        ).first()

        if existing_binding:
            logger.warning(f"群聊绑定已存在: case_id={case_id}, chat_id={chat_id}")
            raise ValidationException(
                message="该群聊已绑定到此案件",
                code="CHAT_ALREADY_BOUND",
                errors={"case_id": case_id, "chat_id": chat_id, "existing_binding_id": existing_binding.id},
            )

        # 如果没有提供群聊名称，尝试从平台获取
        if not chat_name:
            try:
                provider = self.factory.get_provider(platform)
                if provider.is_available():
                    result = provider.get_chat_info(chat_id)
                    if result.success and result.chat_name:
                        chat_name = result.chat_name
                        logger.debug(f"从平台获取群聊名称: {chat_name}")
                    else:
                        logger.warning(f"无法从平台获取群聊名称: {result.message}")
                else:
                    logger.warning(f"平台提供者不可用，无法获取群聊名称: {platform.value}")
            except Exception as e:
                logger.warning(f"获取群聊信息失败: {e!s}")

        # 如果仍然没有群聊名称，使用默认格式
        if not chat_name:
            chat_name = self._build_chat_name(case)
            logger.debug(f"使用默认群聊名称: {chat_name}")

        # 创建绑定记录
        try:
            with transaction.atomic():
                case_chat = CaseChat.objects.create(
                    case=case, platform=platform, chat_id=chat_id, name=chat_name, is_active=True
                )

                logger.info(
                    f"群聊绑定成功: case_id={case_id}, chat_id={chat_id}, platform={platform.value}, name={chat_name}"
                )

                return case_chat

        except Exception as e:
            logger.error(f"创建群聊绑定记录失败: case_id={case_id}, chat_id={chat_id}, error={e!s}")
            raise ValidationException(
                message="创建群聊绑定记录失败",
                code="BINDING_CREATION_ERROR",
                errors={"case_id": case_id, "chat_id": chat_id, "original_error": str(e)},
            ) from e
