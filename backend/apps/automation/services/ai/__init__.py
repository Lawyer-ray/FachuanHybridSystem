"""
AI 服务模块
"""

from .ollama_config import OllamaConfig, get_ollama_base_url, get_ollama_model

__all__ = [
    "OllamaConfig",
    "get_ollama_model",
    "get_ollama_base_url",
]
