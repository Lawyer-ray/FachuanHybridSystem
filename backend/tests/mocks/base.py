"""
Mock 服务基类
"""

from typing import Any, Dict, List, Optional
from unittest.mock import Mock


class MockService:
    """
    Mock 服务基类

    提供基础的 Mock 功能，用于测试时隔离依赖

    使用方法：
        class MyMockService(MockService):
            def get_data(self, id):
                return self._get_mock_return('get_data', {'id': id})

        mock = MyMockService()
        mock.set_return('get_data', {'data': 'test'})
        result = mock.get_data(1)  # 返回 {'data': 'test'}
    """

    def __init__(self):
        """初始化 Mock 服务"""
        self._mock_returns: Dict[str, Any] = {}
        self._mock_side_effects: Dict[str, Any] = {}
        self._call_history: List[Dict[str, Any]] = []

    def set_return(self, method_name: str, return_value: Any) -> None:
        """
        设置方法的返回值

        Args:
            method_name: 方法名
            return_value: 返回值
        """
        self._mock_returns[method_name] = return_value

    def set_side_effect(self, method_name: str, side_effect: Any) -> None:
        """
        设置方法的副作用（异常或可调用对象）

        Args:
            method_name: 方法名
            side_effect: 副作用（异常或可调用对象）
        """
        self._mock_side_effects[method_name] = side_effect

    def _get_mock_return(self, method_name: str, args: Dict[str, Any]) -> Any:
        """
        获取 Mock 方法的返回值

        Args:
            method_name: 方法名
            args: 方法参数

        Returns:
            返回值

        Raises:
            如果设置了副作用异常，则抛出该异常
        """
        # 记录调用历史
        self._call_history.append({"method": method_name, "args": args})

        # 检查是否有副作用
        if method_name in self._mock_side_effects:
            side_effect = self._mock_side_effects[method_name]
            if isinstance(side_effect, Exception):
                raise side_effect
            elif callable(side_effect):
                return side_effect(**args)

        # 返回预设的返回值
        if method_name in self._mock_returns:
            return self._mock_returns[method_name]

        # 默认返回 None
        return None

    def get_call_count(self, method_name: str) -> int:
        """
        获取方法的调用次数

        Args:
            method_name: 方法名

        Returns:
            调用次数
        """
        return sum(1 for call in self._call_history if call["method"] == method_name)

    def get_call_args(self, method_name: str, call_index: int = 0) -> Optional[Dict[str, Any]]:
        """
        获取方法的调用参数

        Args:
            method_name: 方法名
            call_index: 调用索引（0 表示第一次调用）

        Returns:
            调用参数字典，如果没有调用则返回 None
        """
        calls = [call for call in self._call_history if call["method"] == method_name]
        if call_index < len(calls):
            return calls[call_index]["args"]
        return None

    def reset(self) -> None:
        """重置 Mock 状态"""
        self._mock_returns.clear()
        self._mock_side_effects.clear()
        self._call_history.clear()
