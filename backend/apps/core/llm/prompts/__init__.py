"""
Prompt 管理模块

提供 Prompt 模板的注册、获取和渲染功能.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

# 导入各场景 Prompt 模块,确保模板在导入时自动注册
from . import automation, litigation
from .base import CodePromptTemplate, PromptManager

__all__ = [
    "automation",
    "litigation",
    "CodePromptTemplate",
    "PromptManager",
]
