"""
AI 服务模块
"""

from .ollama_config import OllamaConfig, get_ollama_model, get_ollama_base_url

__all__ = [
    'OllamaConfig',
    'get_ollama_model', 
    'get_ollama_base_url',
]
