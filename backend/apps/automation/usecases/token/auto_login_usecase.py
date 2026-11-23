"""Stub: AutoLoginUsecase has been moved to plugins/court_automation/token/auto_login_usecase.py

This file re-exports from the plugin for backward compatibility.

S01-09（2026-11-23 二轮审计）建议把这里的 ``except ImportError`` 兜底改成「导入失败直接抛」，
理由是缺插件时 ``AutoLoginUsecase``/``RetryConfig`` 变成 ``None``，错误会拖到 ``RetryConfig()``
处才炸成「'NoneType' object is not callable」，堆栈指不到真实原因。

**该改法不予采纳（改过又回退，见 2026-11-23 CI 三红）**：``backend/plugins`` 是内部私有子模块、
不对外提供（README / INSTALL 已写明），CI 与外部部署都没有它；模块级 raise 会让所有
``from apps.automation.usecases.token.auto_login_usecase import ...`` 在**收集阶段**就
ImportError（实测：两个测试模块收集中断，backend / backend-unit-coverage /
backend-integration-smoke 三个 job 红）。

正解方向：**保持导入可用**（缺插件时降级为本文件的 ``None``），把「缺插件」的可诊断错误
放在**调用点**（如 ``apps/core/dependencies/automation_token.py`` 在用到 ``RetryConfig`` 前
显式判断插件可用性并抛带说明的错误）。这属于待办，不在本文件解决。
"""

from __future__ import annotations

from typing import Any

AutoLoginUsecase: Any
RetryConfig: Any

try:
    from plugins.court_automation.token.auto_login_usecase import AutoLoginUsecase as _AutoLoginUsecase
    from plugins.court_automation.token.auto_login_usecase import RetryConfig as _RetryConfig

    AutoLoginUsecase = _AutoLoginUsecase
    RetryConfig = _RetryConfig
except ImportError:  # pragma: no cover - 取决于是否安装内部插件
    # 缺插件时降级为 None（见文件头：不能在导入点抛，否则 CI / 外部部署整片收集中断）。
    # 两个名字先声明为 Any，是为了让「装插件 / 不装插件」两种环境下 mypy 都不报
    # 「赋值不兼容」或「type: ignore 多余」——两边的诊断恰好相反，只能绕开。
    AutoLoginUsecase = None
    RetryConfig = None
