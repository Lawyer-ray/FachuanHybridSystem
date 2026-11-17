"""OA filing 服务工厂函数。

`ScriptExecutorService` 的装配唯一入口。contracts / client 等跨 app 消费方通过本模块取实例，
不各自 `ScriptExecutorService()`（四层架构禁止 admin/api 层直接实例化 Service）。
"""

from __future__ import annotations

from .script_executor_service import ScriptExecutorService


def build_script_executor_service() -> ScriptExecutorService:
    """构建 OA 通用调度器实例（无状态，可安全缓存）。"""
    return ScriptExecutorService()
