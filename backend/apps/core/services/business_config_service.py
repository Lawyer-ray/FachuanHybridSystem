"""
业务配置服务

提供业务配置的服务层封装,符合四层架构规范.
"""

import logging
from typing import Any, cast

logger = logging.getLogger(__name__)


class BusinessConfigService:
    """业务配置服务

    封装 BusinessConfig 的调用,支持依赖注入.

    Attributes:
        _config: BusinessConfig 实例(可选注入)
    """

    def __init__(self, config: Any | None = None) -> None:
        """初始化服务

        Args:
            config: BusinessConfig 实例,用于依赖注入(测试时使用)
        """
        self._config_instance = config

    @property
    def _config(self) -> Any:
        """延迟加载 BusinessConfig 实例"""
        if self._config_instance is None:
            from apps.core.business_config import BusinessConfig

            self._config_instance = BusinessConfig()
        return self._config_instance

    def get_stages_for_case_type(self, case_type: str | None) -> list[tuple[str, str]]:
        """获取指定案件类型可用的阶段列表

        Args:
            case_type: 案件类型代码,None 表示返回所有

        Returns:
            [(value, label), ...] 列表
        """
        return cast(list[tuple[str, str]], self._config.get_stages_for_case_type(case_type))

    def get_legal_statuses_for_case_type(self, case_type: str | None) -> list[tuple[str, str]]:
        """获取指定案件类型可用的诉讼地位列表

        Args:
            case_type: 案件类型代码,None 表示返回所有

        Returns:
            [(value, label), ...] 列表
        """
        return cast(list[tuple[str, str]], self._config.get_legal_statuses_for_case_type(case_type))

    def get_stage_label(self, value: str) -> str:
        """获取阶段显示名称

        Args:
            value: 阶段代码

        Returns:
            阶段显示名称
        """
        return cast(str, self._config.get_stage_label(value))

    def get_legal_status_label(self, value: str) -> str:
        """获取诉讼地位显示名称

        Args:
            value: 诉讼地位代码

        Returns:
            诉讼地位显示名称
        """
        return cast(str, self._config.get_legal_status_label(value))

    def is_stage_valid_for_case_type(self, stage: str, case_type: str | None) -> bool:
        """检查阶段是否适用于指定案件类型

        Args:
            stage: 阶段代码
            case_type: 案件类型代码

        Returns:
            是否适用
        """
        return cast(bool, self._config.is_stage_valid_for_case_type(stage, case_type))

    def is_legal_status_valid_for_case_type(self, status: str, case_type: str | None) -> bool:
        """检查诉讼地位是否适用于指定案件类型

        Args:
            status: 诉讼地位代码
            case_type: 案件类型代码

        Returns:
            是否适用
        """
        return cast(bool, self._config.is_legal_status_valid_for_case_type(status, case_type))

    def get_compatible_legal_statuses(
        self,
        existing_statuses: list[str],
        case_type: str | None = None,
    ) -> list[tuple[str, str]]:
        """根据已有诉讼地位获取兼容的诉讼地位列表

        Args:
            existing_statuses: 案件中已有当事人的诉讼地位列表
            case_type: 案件类型(用于基础过滤)

        Returns:
            [(value, label), ...] 兼容的诉讼地位列表
        """
        return cast(list[tuple[str, str]], self._config.get_compatible_legal_statuses(existing_statuses, case_type))

    def is_legal_status_compatible(
        self,
        new_status: str,
        existing_statuses: list[str],
    ) -> bool:
        """检查新诉讼地位是否与已有诉讼地位兼容

        Args:
            new_status: 要添加的诉讼地位
            existing_statuses: 已有的诉讼地位列表

        Returns:
            True 如果兼容,False 如果不兼容
        """
        return cast(bool, self._config.is_legal_status_compatible(new_status, existing_statuses))

    # 内部方法供适配器调用
    def get_stages_for_case_type_internal(self, case_type: str | None) -> list[tuple[str, str]]:
        """内部方法:获取阶段列表(供适配器调用)"""
        return self.get_stages_for_case_type(case_type)

    def get_legal_statuses_for_case_type_internal(self, case_type: str | None) -> list[tuple[str, str]]:
        """内部方法:获取诉讼地位列表(供适配器调用)"""
        return self.get_legal_statuses_for_case_type(case_type)
