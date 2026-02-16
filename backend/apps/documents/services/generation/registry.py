"""Business logic services."""

from __future__ import annotations

"""
生成器注册表

管理所有可用的文书生成器,支持自动发现和手动注册.
实现单例模式,确保全局唯一的注册表实例.
"""


import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING, Any, ClassVar

from apps.core.exceptions import ConflictError, NotFoundError
from apps.core.path import Path

if TYPE_CHECKING:
    from .base_generator import BaseGenerator

logger = logging.getLogger(__name__)


class GeneratorRegistry:
    """
    生成器注册表

    管理所有可用的文书生成器,支持自动发现和手动注册.
    使用单例模式确保全局唯一性.
    """

    _instance: GeneratorRegistry | None = None
    _generators: ClassVar[dict[str, type[BaseGenerator]]] = {}

    def __new__(cls) -> GeneratorRegistry:
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._generators = {}  # type: ignore[misc]
        return cls._instance

    @classmethod
    def register(cls, generator_class: type[BaseGenerator]) -> type[BaseGenerator]:
        """
        注册生成器的装饰器

        Usage:
            @GeneratorRegistry.register
            class ContractGenerator(BaseGenerator):
                name = "contract_generator"
                ...

        Args:
            generator_class: 生成器类

        Returns:
            原生成器类(支持链式调用)

        Raises:
            ValueError: 生成器未定义 name 属性
            ConflictError: 生成器名称已存在
        """
        instance = cls()
        name = getattr(generator_class, "name", "")

        if not name:
            raise ValueError(f"生成器 {generator_class.__name__} 必须定义 name 属性")

        if name in instance._generators:
            raise ConflictError(
                message=f"生成器名称冲突: {name}",
                code="GENERATOR_NAME_CONFLICT",
                errors={"name": f"生成器 '{name}' 已被注册"},
            )

        instance._generators[name] = generator_class
        logger.info(f"注册生成器: {name} ({generator_class.__name__})")
        return generator_class

    def get_generator(self, name: str) -> BaseGenerator:
        """
        获取生成器实例

        Args:
            name: 生成器名称

        Returns:
            生成器实例

        Raises:
            NotFoundError: 生成器不存在
        """
        if name not in self._generators:
            raise NotFoundError(
                message=f"生成器不存在: {name}",
                code="GENERATOR_NOT_FOUND",
                errors={"name": f"未找到名为 '{name}' 的生成器"},
            )
        return self._generators[name]()

    def list_generators(self) -> list[str]:
        """
        列出所有已注册的生成器名称

        Returns:
            生成器名称列表
        """
        return list(self._generators.keys())

    def get_generators_for_template_type(self, template_type: str) -> list[BaseGenerator]:
        """
        获取指定模板类型的所有生成器

        Args:
            template_type: 模板类型(如 'contract', 'case', 'authorization')

        Returns:
            生成器实例列表
        """
        return [cls() for cls in self._generators.values() if getattr(cls, "template_type", "") == template_type]

    def get_generators_by_category(self, category: str) -> list[BaseGenerator]:
        """
        获取指定分类的所有生成器

        Args:
            category: 生成器分类(如 'litigation', 'non_litigation', 'general')

        Returns:
            生成器实例列表
        """
        return [cls() for cls in self._generators.values() if getattr(cls, "category", "") == category]

    @classmethod
    def auto_discover(cls) -> None:
        """
        自动发现并加载 generators 目录下的所有生成器

        扫描 generators 目录下的所有 Python 模块,自动导入以触发生成器注册.
        忽略加载失败的模块,但会记录错误日志.
        """
        generators_path = Path(__file__).parent / "generators"
        if not generators_path.exists():
            logger.warning(f"生成器目录不存在: {generators_path}")
            return

        logger.debug(f"开始自动发现生成器,目录: {generators_path}")

        for module_info in pkgutil.iter_modules([str(generators_path)]):
            module_name = module_info.name
            try:
                # 导入模块以触发装饰器注册
                importlib.import_module(f".generators.{module_name}", package=__package__)
                logger.debug(f"加载生成器模块: {module_name}")
            except Exception as e:
                logger.error(f"加载生成器模块失败: {module_name}, 错误: {e}")

    def clear_registry(self) -> None:
        """
        清空注册表(主要用于测试)

        Warning:
            此方法会清空所有已注册的生成器,仅在测试环境中使用.
        """
        self._generators.clear()
        logger.debug("生成器注册表已清空")

    def get_registry_info(self) -> dict[str, dict[str, str]]:
        """
        获取注册表信息

        Returns:
            包含所有生成器信息的字典,格式为:
            {
                "generator_name": {
                    "class_name": "ClassName",
                    "display_name": "显示名称",
                    "description": "描述",
                    "category": "分类",
                    "template_type": "模板类型"
                }
            }
        """
        info: dict[str, Any] = {}
        for name, cls in self._generators.items():
            info[name] = {
                "class_name": cls.__name__,
                "display_name": getattr(cls, "display_name", ""),
                "description": getattr(cls, "description", ""),
                "category": getattr(cls, "category", ""),
                "template_type": getattr(cls, "template_type", ""),
            }
        return info

    def __len__(self) -> int:
        """返回已注册生成器的数量"""
        return len(self._generators)

    def __contains__(self, name: str) -> bool:
        """检查生成器是否已注册"""
        return name in self._generators

    def __str__(self) -> str:
        """字符串表示"""
        return f"GeneratorRegistry({len(self._generators)} generators)"

    def __repr__(self) -> str:
        """调试表示"""
        return f"<GeneratorRegistry: {list(self._generators.keys())}>"


# 模块加载时自动发现生成器
GeneratorRegistry.auto_discover()
