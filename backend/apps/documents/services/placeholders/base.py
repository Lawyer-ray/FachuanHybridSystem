"""
占位符服务基类

定义占位符服务的抽象接口和基础功能.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar


class BasePlaceholderService(ABC):
    """占位符服务基类"""

    # 服务元信息(子类必须定义)
    name: str = ""  # 服务名称(唯一标识)
    display_name: str = ""  # 显示名称
    description: str = ""  # 描述
    category: str = "general"  # 分类:basic, party, lawyer, contract
    placeholder_keys: ClassVar[list[str]] = []  # 此服务生成的占位符键列表
    placeholder_metadata: ClassVar[dict[str, dict[str, Any]]] = {}

    @abstractmethod
    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成占位符值

        Args:
            context_data: 包含原始数据的上下文(如 contract, clients 等)

        Returns:
            包含占位符键值对的字典
        """
        pass

    def get_placeholder_keys(self) -> list[str]:
        """返回此服务生成的占位符键列表"""
        return self.placeholder_keys.copy()

    def get_placeholder_metadata(self) -> dict[str, dict[str, Any]]:
        return {k: dict[str, Any](v) for k, v in (self.placeholder_metadata or {}).items()}

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.name})"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.name}>"
