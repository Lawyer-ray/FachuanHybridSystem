from __future__ import annotations

from django.utils.translation import gettext_lazy as _


class OAFilingError(Exception):
    """OA立案基础异常"""

    def __init__(self, message: str = "") -> None:
        self.message: str = message
        super().__init__(self.message)


class ScriptExecutionError(OAFilingError):
    """脚本执行失败"""

    def __init__(self, message: str = str(_("脚本执行失败"))) -> None:
        super().__init__(message)
