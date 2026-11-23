"""Stub: AutoLoginUsecase has been moved to plugins/court_automation/token/auto_login_usecase.py

This file re-exports from the plugin for backward compatibility.

S01-09（2026-11-23 二轮审计）：原实现用 ``except ImportError`` 把 AutoLoginUsecase /
RetryConfig 静默替换成 None，缺 plugins 的环境下错误会拖到 ``RetryConfig()`` 处才炸成
「'NoneType' object is not callable」，堆栈完全指不到真实原因。现在导入失败直接抛，
让缺插件的错误在导入点就带原名暴露。
"""

from plugins.court_automation.token.auto_login_usecase import *  # noqa: F403
from plugins.court_automation.token.auto_login_usecase import AutoLoginUsecase, RetryConfig
