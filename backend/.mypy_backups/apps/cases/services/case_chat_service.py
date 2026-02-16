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

import logging
from typing import Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.automation.services.chat.base import ChatResult, MessageContent
from apps.automation.services.chat.factory import ChatProviderFactory
from apps.cases.exceptions import ChatCreationException, MessageSendException
from apps.cases.models import Case, CaseChat
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

    def __init__(self):
        """初始化案件群聊服务"""
        self.factory = ChatProviderFactory
        logger.debug("CaseChatService 初始化完成")

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
        except ObjectDoesNotExist:
            logger.error(f"案件不存在: ID={case_id}")
            raise NotFoundError(message=f"案件不存在: ID={case_id}", code="CASE_NOT_FOUND", errors={"case_id": case_id})

    def create_chat_for_case(
        self, case_id: int, platform: ChatPlatform = ChatPlatform.FEISHU, owner_id: Optional[str] = None
    ) -> CaseChat:
        """为案件创建群聊

        通过群聊提供者工厂获取对应平台的提供者，创建群聊并保存记录。
        使用数据库事务确保群聊创建和数据持久化的一致性。

        Args:
            case_id: 案件ID
            platform: 群聊平台，默认为飞书
            owner_id: 群主ID（可选，某些平台需要）

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

        # 获取案件对象
        case = self._get_case(case_id)

        # 生成群聊名称
        chat_name = self._build_chat_name(case)

        # 如果没有指定群主，使用默认群主配置
        if not owner_id:
            from django.conf import settings

            # 尝试使用统一配置管理器
            try:
                if getattr(settings, "CONFIG_MANAGER_AVAILABLE", False):
                    get_unified_config = getattr(settings, "get_unified_config", None)
                    if get_unified_config:
                        default_owner = get_unified_config("features.case_chat.default_owner_id")
                        if default_owner:
                            owner_id = default_owner
                            logger.debug(f"使用默认群主（统一配置）: {owner_id}")
                        return
            except Exception as e:
                logger.debug(f"从统一配置获取默认群主失败: {e}")

            # 回退到传统配置方式
            default_owner = getattr(settings, "CASE_CHAT", {}).get("DEFAULT_OWNER_ID")
            if default_owner:
                owner_id = default_owner
                logger.debug(f"使用默认群主: {owner_id}")

        # 获取群聊提供者
        try:
            provider = self.factory.get_provider(platform)
        except Exception as e:
            logger.error(f"获取群聊提供者失败: platform={platform.value}, error={str(e)}")
            raise ChatCreationException(
                message=f"无法获取群聊提供者: {platform.label}",
                code="PROVIDER_UNAVAILABLE",
                platform=platform.value,
                errors={"original_error": str(e)},
            ) from e

        # 检查提供者是否可用
        if not provider.is_available():
            logger.error(f"群聊提供者不可用: platform={platform.value}")
            raise ChatCreationException(
                message=f"群聊平台不可用: {platform.label}",
                code="PROVIDER_NOT_AVAILABLE",
                platform=platform.value,
                errors={"platform_status": "配置不完整或服务不可用"},
            )

        # 使用数据库事务确保一致性
        try:
            with transaction.atomic():
                # 调用提供者创建群聊
                logger.debug(f"调用提供者创建群聊: name={chat_name}")
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

                # 创建数据库记录
                case_chat = CaseChat.objects.create(
                    case=case,
                    platform=platform,
                    chat_id=result.chat_id,
                    name=result.chat_name or chat_name,
                    is_active=True,
                )

                logger.info(
                    f"群聊创建成功: case_id={case_id}, chat_id={result.chat_id}, "
                    f"platform={platform.value}, name={case_chat.name}"
                )

                return case_chat

        except ChatCreationException:
            # 重新抛出业务异常
            raise
        except Exception as e:
            logger.error(f"创建群聊时发生未预期错误: case_id={case_id}, error={str(e)}")
            raise ChatCreationException(
                message="创建群聊时发生系统错误",
                code="SYSTEM_ERROR",
                platform=platform.value,
                errors={"case_id": case_id, "original_error": str(e)},
            ) from e

    def get_or_create_chat(
        self, case_id: int, platform: ChatPlatform = ChatPlatform.FEISHU, owner_id: Optional[str] = None
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
        case = self._get_case(case_id)

        # 查找现有的活跃群聊
        existing_chat = CaseChat.objects.filter(case_id=case_id, platform=platform, is_active=True).first()

        if existing_chat:
            logger.debug(f"找到现有群聊: chat_id={existing_chat.chat_id}, " f"name={existing_chat.name}")
            return existing_chat

        # 不存在则创建新群聊
        logger.info(f"未找到现有群聊，开始创建新群聊: case_id={case_id}, platform={platform.value}")
        return self.create_chat_for_case(case_id, platform, owner_id)

    def send_document_notification(
        self,
        case_id: int,
        sms_content: str,
        document_paths: list = None,
        platform: ChatPlatform = ChatPlatform.FEISHU,
        title: str = "📋 法院文书通知",
    ) -> ChatResult:
        """发送文书通知到群聊

        获取或创建指定案件的群聊，然后发送文书通知消息。
        支持同时发送文本消息和多个文件附件。

        Args:
            case_id: 案件ID
            sms_content: 短信内容（作为消息正文）
            document_paths: 文书文件路径列表（可选）
            platform: 群聊平台，默认为飞书
            title: 消息标题，默认为"📋 法院文书通知"

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
                sms_content="您有新的法院文书，请及时查看。",
                document_paths=["/path/to/document1.pdf", "/path/to/document2.pdf"]
            )
            if result.success:
                print("通知发送成功")
        """
        logger.info(
            f"发送文书通知: case_id={case_id}, platform={platform.value}, "
            f"file_count={len(document_paths) if document_paths else 0}"
        )

        # 验证必填参数
        if not sms_content or not sms_content.strip():
            raise ValidationException(
                message="短信内容不能为空", code="INVALID_SMS_CONTENT", errors={"sms_content": "短信内容为必填项"}
            )

        # 获取或创建群聊
        try:
            chat = self.get_or_create_chat(case_id, platform)
        except Exception as e:
            logger.error(f"获取或创建群聊失败: case_id={case_id}, error={str(e)}")
            raise

        # 获取群聊提供者
        try:
            provider = self.factory.get_provider(platform)
        except Exception as e:
            logger.error(f"获取群聊提供者失败: platform={platform.value}, error={str(e)}")
            raise MessageSendException(
                message=f"无法获取群聊提供者: {platform.label}",
                code="PROVIDER_UNAVAILABLE",
                platform=platform.value,
                chat_id=chat.chat_id,
                errors={"original_error": str(e)},
            ) from e

        # 构建消息内容（暂时不包含文件，文件单独发送）
        content = MessageContent(title=title, text=sms_content.strip(), file_path=None)  # 文件将单独发送

        # 发送消息（带重试机制处理群聊解散情况）
        try:
            logger.debug(f"发送消息到群聊: chat_id={chat.chat_id}, title={title}")
            result = provider.send_message(chat.chat_id, content)

            if not result.success:
                logger.error(
                    f"消息发送失败: chat_id={chat.chat_id}, "
                    f"message={result.message}, error_code={result.error_code}"
                )

                # 检查是否是群聊不存在的错误（群聊可能已解散）
                if self._is_chat_not_found_error(result):
                    logger.warning(f"群聊可能已解散，尝试创建新群聊: chat_id={chat.chat_id}")

                    # 标记旧群聊为非活跃状态
                    chat.is_active = False
                    chat.save()

                    # 创建新群聊并重试发送
                    try:
                        new_chat = self.create_chat_for_case(case_id, platform)
                        logger.info(
                            f"创建新群聊成功，重试发送消息: old_chat_id={chat.chat_id}, "
                            f"new_chat_id={new_chat.chat_id}"
                        )

                        # 使用新群聊重试发送消息
                        result = provider.send_message(new_chat.chat_id, content)
                        chat = new_chat  # 更新chat引用，用于后续文件发送

                        if result.success:
                            logger.info(f"重试发送消息成功: new_chat_id={new_chat.chat_id}")
                        else:
                            logger.error(f"重试发送消息仍然失败: new_chat_id={new_chat.chat_id}")

                    except Exception as retry_error:
                        logger.error(f"创建新群聊或重试发送失败: {str(retry_error)}")
                        # 如果重试也失败，抛出原始错误
                        raise MessageSendException(
                            message=f"群聊已解散，重新创建群聊失败: {str(retry_error)}",
                            code="CHAT_RECREATE_FAILED",
                            platform=platform.value,
                            chat_id=chat.chat_id,
                            error_code=result.error_code,
                            errors={
                                "original_error": result.message,
                                "retry_error": str(retry_error),
                                "provider_response": result.raw_response,
                            },
                        )

                # 如果不是群聊不存在的错误，或重试后仍然失败，抛出异常
                if not result.success:
                    raise MessageSendException(
                        message=result.message or "消息发送失败",
                        code="MESSAGE_SEND_FAILED",
                        platform=platform.value,
                        chat_id=chat.chat_id,
                        error_code=result.error_code,
                        errors={"provider_response": result.raw_response, "content_title": title},
                    )

            # 如果有文件且消息发送成功，逐个发送所有文件
            if document_paths and result.success:
                logger.info(f"开始发送 {len(document_paths)} 个文件到群聊: chat_id={chat.chat_id}")

                successful_files = 0
                failed_files = 0

                for i, file_path in enumerate(document_paths, 1):
                    logger.debug(f"发送第 {i}/{len(document_paths)} 个文件: {file_path}")

                    try:
                        file_result = provider.send_file(chat.chat_id, file_path)

                        if file_result.success:
                            successful_files += 1
                            logger.info(f"文件发送成功 ({i}/{len(document_paths)}): {file_path}")
                        else:
                            failed_files += 1
                            logger.warning(
                                f"文件发送失败 ({i}/{len(document_paths)}): {file_path}, "
                                f"错误: {file_result.message}"
                            )
                    except Exception as e:
                        failed_files += 1
                        logger.error(f"文件发送异常 ({i}/{len(document_paths)}): {file_path}, " f"错误: {str(e)}")

                # 更新结果消息
                if successful_files == len(document_paths):
                    result.message = f"消息和所有文件发送成功 ({successful_files} 个文件)"
                    logger.info(f"所有文件发送成功: chat_id={chat.chat_id}, 成功 {successful_files} 个")
                elif successful_files > 0:
                    result.message = f"消息发送成功，部分文件发送成功 ({successful_files}/{len(document_paths)} 个文件)"
                    logger.warning(
                        f"部分文件发送失败: chat_id={chat.chat_id}, "
                        f"成功 {successful_files}/{len(document_paths)} 个"
                    )
                else:
                    result.message = f"消息发送成功，但所有文件发送失败 ({failed_files} 个文件)"
                    logger.error(f"所有文件发送失败: chat_id={chat.chat_id}, 失败 {failed_files} 个")

            logger.info(f"文书通知发送完成: case_id={case_id}, chat_id={chat.chat_id}, " f"success={result.success}")

            return result

        except MessageSendException:
            # 重新抛出业务异常
            raise
        except Exception as e:
            logger.error(f"发送文书通知时发生未预期错误: case_id={case_id}, " f"chat_id={chat.chat_id}, error={str(e)}")
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
                print("群聊绑定已解除")
        """
        logger.info(f"解除群聊绑定: chat_id={chat_id}")

        # 验证参数
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
            logger.error(f"解除群聊绑定时发生错误: chat_id={chat_id}, error={str(e)}")
            raise ValidationException(
                message="解除群聊绑定时发生系统错误",
                code="SYSTEM_ERROR",
                errors={"chat_id": chat_id, "original_error": str(e)},
            ) from e

    def bind_existing_chat(
        self, case_id: int, platform: ChatPlatform, chat_id: str, chat_name: Optional[str] = None
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
        logger.info(f"绑定已存在的群聊: case_id={case_id}, platform={platform.value}, " f"chat_id={chat_id}")

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
                logger.warning(f"获取群聊信息失败: {str(e)}")

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
                    f"群聊绑定成功: case_id={case_id}, chat_id={chat_id}, "
                    f"platform={platform.value}, name={chat_name}"
                )

                return case_chat

        except Exception as e:
            logger.error(f"创建群聊绑定记录失败: case_id={case_id}, chat_id={chat_id}, " f"error={str(e)}")
            raise ValidationException(
                message="创建群聊绑定记录失败",
                code="BINDING_CREATION_ERROR",
                errors={"case_id": case_id, "chat_id": chat_id, "original_error": str(e)},
            ) from e
