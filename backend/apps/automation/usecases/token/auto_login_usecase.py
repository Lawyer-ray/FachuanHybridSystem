"""Stub: AutoLoginUsecase has been moved to plugins/court_automation/token/auto_login_usecase.py

This file re-exports from the plugin for backward compatibility.

S01-09（2026-11-23 二轮审计）指出：原实现用 ``except ImportError`` 把 AutoLoginUsecase /
RetryConfig 静默替换成 ``None``，缺插件时错误会拖到 ``RetryConfig()`` 处才炸成
「'NoneType' object is not callable」，堆栈指不到真实原因。

但**直接在模块级抛出也不行**：`backend/plugins` 是内部私有子模块，不对外提供
（见 README / INSTALL），CI 与外部部署本来就没有它，模块级 raise 会让所有
`import apps.automation.usecases.token.auto_login_usecase` 的代码在**收集阶段**就崩
（实测 CI：两个测试模块 ImportError 收集中断）。

所以取两者之间：**导入保持可用**（缺插件时用占位符），**一旦真去构造就抛带原因的错误**——
既不会在缺插件环境下阻断无关代码，也不会把「NoneType 不可调用」这种无信息量的错误留到远处。
"""

from __future__ import annotations

try:
    from plugins.court_automation.token.auto_login_usecase import *  # noqa: F403
    from plugins.court_automation.token.auto_login_usecase import AutoLoginUsecase, RetryConfig
except ImportError as _plugins_import_error:  # pragma: no cover - 取决于是否安装内部插件
    # PEP 3110：`as e` 在 except 块结束即被删除，必须先存到模块级变量再给类体引用
    _PLUGIN_IMPORT_ERROR: BaseException | None = _plugins_import_error

    class _MissingCourtAutomationPlugin:
        """缺插件时的占位：构造即抛出可诊断的错误（而不是让 None 拖到调用点）。"""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError(
                "plugins.court_automation 不可用（内部插件，不对外提供）："
                "AutoLoginUsecase / RetryConfig 需要 backend/plugins 子模块"
            ) from _PLUGIN_IMPORT_ERROR

    AutoLoginUsecase = _MissingCourtAutomationPlugin  # type: ignore[assignment,misc]
    RetryConfig = _MissingCourtAutomationPlugin  # type: ignore[assignment,misc]
