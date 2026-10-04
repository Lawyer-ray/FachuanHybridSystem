"""Business logic services."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from apps.core.exceptions import ValidationException

from .fallback import (
    PLACEHOLDER_FALLBACK_VALUE,
    ensure_required_placeholders,
    get_service_placeholder_keys,
    normalize_service_result,
)
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
        self,
        context_data: PlaceholderContextData | dict[str, Any],
        required_placeholders: list[str] | None = None,
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

        context_data = self._normalize_context_data(context_data)
        context: dict[str, Any] = {}
        services = self._get_relevant_services(required_placeholders)

        for service in services:
            service_keys = get_service_placeholder_keys(service)
            try:
                service_result = service.generate(context_data)
                normalized_result = normalize_service_result(service_result, expected_keys=service_keys)
                owned_result = self._owned_result(service, normalized_result)
                if owned_result:
                    context.update(owned_result)
                    logger.debug("服务 %s 生成了 %s 个占位符", service.name, len(owned_result))
            except Exception as e:
                logger.error(
                    "占位符服务执行失败: %s",
                    service.name,
                    extra={
                        "service_name": service.name,
                        "error": str(e),
                        "context_keys": list(context_data.keys()),
                    },
                    exc_info=True,
                )
                context.update(self._owned_result(service, dict.fromkeys(service_keys, PLACEHOLDER_FALLBACK_VALUE)))
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

        final_context = ensure_required_placeholders(context, required_placeholders)

        logger.info("上下文构建完成,生成了 %s 个占位符", len(final_context))
        return final_context

    def _normalize_context_data(
        self, context_data: PlaceholderContextData | dict[str, Any]
    ) -> PlaceholderContextData | dict[str, Any]:
        """标准化上下文,对常见缺失键进行兜底补全."""
        normalized: dict[str, Any] = dict(context_data)

        if normalized.get("case_id") is None:
            case_obj = normalized.get("case")
            case_id = getattr(case_obj, "id", None)
            if case_id is not None:
                normalized["case_id"] = case_id

        return normalized

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
            from apps.documents.services.infrastructure.wiring import get_contract_service

            contract_service = get_contract_service()
            # adapter 无 get_contract_internal（那是 query_service 的方法），调公开的 get_contract
            contract_dto = contract_service.get_contract(contract_id)

            if not contract_dto:
                raise ValidationException(
                    message="合同不存在",
                    code="CONTRACT_NOT_FOUND",
                    errors={"contract_id": f"ID 为 {contract_id} 的合同不存在"},
                )

            contract = contract_service.get_contract_model_internal(contract_id)
            if not contract:
                raise ValidationException(
                    message="合同不存在",
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
                message="构建合同上下文失败",
                code="CONTEXT_BUILD_ERROR",
                errors={"contract_id": f"合同 {contract_id} 上下文构建失败: {e!s}"},
            ) from e

    def _owned_result(self, service: Any, result: Mapping[str, Any]) -> dict[str, Any]:
        """
        过滤服务返回值,只保留该服务拥有归属权的占位符键。

        多个服务声明同一键时,注册表在注册阶段按确定性规则裁决出唯一归属服务;
        非归属服务的同键输出会被丢弃,避免按执行顺序互相覆盖
        (如合同流中诉讼服务把「案由」覆盖为兜底值 "/" 的问题)。
        注册表未提供归属查询时不做过滤,保持原行为。
        """
        get_owner = getattr(self.registry, "get_placeholder_key_owner", None)
        if not callable(get_owner):
            return dict(result)

        service_name = getattr(service, "name", "")
        return {key: value for key, value in result.items() if get_owner(key) in (None, service_name)}

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

        # 根据占位符键查找相关服务(按服务类型去重,注册表每次返回新实例,不能按对象身份去重)
        relevant_services: list[Any] = []
        seen_service_types: set[type[Any]] = set()
        for placeholder_key in required_placeholders:
            service = self.registry.get_service_for_placeholder(placeholder_key)
            if service is None:
                continue
            service_type = type(service)
            if service_type in seen_service_types:
                continue
            seen_service_types.add(service_type)
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
