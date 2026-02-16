"""
LLM 后端模块

提供统一的 LLM 后端抽象层,支持多种后端实现.

Requirements: 1.1
"""

from __future__ import annotations

from typing import Any

from .base import BackendConfig, ILLMBackend, LLMResponse, LLMStreamChunk, LLMUsage
from .moonshot import MoonshotBackend
from .ollama import OllamaBackend

_siliconflow_import_error: Exception | None = None
try:
    from .siliconflow import SiliconFlowBackend
except Exception as exc:
    _siliconflow_import_error = exc

    class SiliconFlowBackend:  # type: ignore[no-redef]
        BACKEND_NAME = "siliconflow"

        def __init__(self, *args, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def, misc]
            self._import_error = _siliconflow_import_error

        def is_available(self) -> bool:
            return False

        def get_default_model(self) -> str:
            return ""

        def chat(self, *args, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
            from apps.core.llm.exceptions import LLMBackendUnavailableError

            raise LLMBackendUnavailableError(
                message="SiliconFlow 后端依赖未安装或导入失败",
                errors={"detail": str(self._import_error)},
            )

        async def achat(self, *args, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
            return self.chat(*args, **kwargs)

        def stream(self, *args, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
            from apps.core.llm.exceptions import LLMBackendUnavailableError

            raise LLMBackendUnavailableError(
                message="SiliconFlow 后端依赖未安装或导入失败",
                errors={"detail": str(self._import_error)},
            )

        async def astream(self, *args, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
            from apps.core.llm.exceptions import LLMBackendUnavailableError

            raise LLMBackendUnavailableError(
                message="SiliconFlow 后端依赖未安装或导入失败",
                errors={"detail": str(self._import_error)},
            )


__all__ = [
    # 基础类
    "ILLMBackend",
    "LLMResponse",
    "LLMStreamChunk",
    "LLMUsage",
    "BackendConfig",
    # 后端实现
    "SiliconFlowBackend",
    "OllamaBackend",
    "MoonshotBackend",
]
