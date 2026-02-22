"""Business logic services."""

from __future__ import annotations
from django.utils.translation import gettext_lazy as _

import logging
from typing import Any

from apps.core.exceptions import ValidationException

from .registry import PlaceholderRegistry
from .types import PlaceholderContextData

logger = logging.getLogger(__name__)


class EnhancedContextBuilder:
    """增强的上下文构建器"""

    def __init__(self, registry: PlaceholderRegistry | None = None) -> None:
        """
        初始化上下文构建器

        Args:
            registry: 占位符注册表实例,如果为 None 则使用默认实例
        """
        self.registry = registry or PlaceholderRegistry()

    def build_context(
        self, context_data: PlaceholderContextData, required_placeholders: list[str] | None = None
    ) -> dict[str, Any]:
        """
        构建完整的替换词上下文

        Args:
            context_data: 原始数据(contract, clients 等)
            required_placeholders: 可选,仅生成指定的占位符

        Returns:
            完整的占位符上下文字典
        """
        if not context_data:
            logger.warning("上下文数据为空")
            return {}

        context: dict[str, Any] = {}
        services = self._get_relevant_services(required_placeholders)

        for service in services:
            try:
                service_result = service.generate(context_data)
                if service_result:
                    context.update(service_result)
                    logger.debug("服务 %s 生成了 %s 个占位符", service.name, len(service_result))
            except Exception as e:
                logger.error(
                    "占位符服务执行失败: %s", service.name,
                    extra={
                        "service_name": service.name,
                        "error": str(e),
                        "context_keys": list(context_data.keys()),
                    },
                    exc_info=True,
                )
                # 继续执行其他服务,不中断整个流程
                continue

        if context_data.get("supplementary_agreement"):
            key_map = {
                "补充协议委托人信息": "委托人信息",
                "补充协议委托人签名盖章信息": "委托人签名盖章信息",
                "补充协议委托人主体信息条款": "委托人主体信息条款",
                "补充协议委托人数量": "委托人数量",
                "补充协议对方当事人主体信息条款": "对方当事人主体信息条款",
            }
            for old_key, new_key in key_map.items():
                if old_key in context:
                    context[new_key] = context[old_key]

        logger.info("上下文构建完成,生成了 %s 个占位符", len(context))
        return context

    def build_contract_context(self, contract_id: int) -> dict[str, Any]:
        """
        为合同构建上下文(便捷方法)

        Args:
            contract_id: 合同 ID

        Returns:
            完整的占位符上下文字典

        Raises:
            ValidationException: 合同不存在或数据无效
        """
        try:
            # 验证合同存在性
            # Requirements: 3.2
            from apps.documents.services.wiring import get_contract_service

            contract_service = get_contract_service()
            contract_dto = contract_service.get_contract_internal(contract_id)

            if not contract_dto:
                raise ValidationException(
                    message=_("合同不存在"),
                    code="CONTRACT_NOT_FOUND",
                    errors={"contract_id": f"ID 为 {contract_id} 的合同不存在"},
                )

            contract = contract_service.get_contract_model_internal(contract_id)
            if not contract:
                raise ValidationException(
                    message=_("合同不存在"),
                    code="CONTRACT_NOT_FOUND",
                    errors={"contract_id": f"ID 为 {contract_id} 的合同不存在"},
                )

            # 构建上下文数据
            context_data: PlaceholderContextData = {"contract": contract, "contract_id": contract_id}

            return self.build_context(context_data)

        except Exception as e:
            if isinstance(e, ValidationException):
                raise

            logger.error("构建合同上下文失败: %s", e, extra={"contract_id": contract_id}, exc_info=True)
            raise ValidationException(
                message=_("构建合同上下文失败"),
                code="CONTEXT_BUILD_ERROR",
                errors={"contract_id": f"合同 {contract_id} 上下文构建失败: {e!s}"},
            ) from e

    def _get_relevant_services(self, required_placeholders: list[str] | None = None) -> Any:
        """
        获取相关的占位符服务

        Args: required_placeholders: 需要的占位符键列表

        Returns:
            相关的服务实例列表
        """
        if not required_placeholders:
            # 如果没有指定占位符,返回所有服务
            return self.registry.get_all_services()

        # 根据占位符键查找相关服务
        relevant_services: list[Any] = []
        for placeholder_key in required_placeholders:
            service = self.registry.get_service_for_placeholder(placeholder_key)
            if service and service not in relevant_services:
                relevant_services.append(service)

        return relevant_services

    def get_available_placeholders(self) -> dict[str, list[str]]:
        """
        获取所有可用的占位符按分类分组

        Returns:
            按分类分组的占位符字典
        """
        result: dict[str, Any] = {}
        services = self.registry.get_all_services()

        for service in services:
            category = service.category
            if category not in result:
                result[category] = []
            result[category].extend(service.get_placeholder_keys())

        return result

    def validate_placeholders(self, placeholder_keys: list[str]) -> dict[str, bool]:
        """
        验证占位符键是否可用

        Args:
            placeholder_keys: 要验证的占位符键列表

        Returns:
            占位符键的可用性字典
        """
        result: dict[str, Any] = {}

        for key in placeholder_keys:
            service = self.registry.get_service_for_placeholder(key)
            result[key] = service is not None

        return result
