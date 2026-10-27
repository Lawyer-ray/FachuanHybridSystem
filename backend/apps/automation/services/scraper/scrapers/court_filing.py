"""法院自动立案爬虫 —— 插件缺失时的**显式失败**占位。

## 为什么是「显式失败」而不是「脚手架实现」

本文件曾被写成一个「看起来能跑」的脚手架：`_login` / `_fill_case_info` /
`_upload_files` 的实现体只有 `logger.info`，从不真正登录、填表、提交，
`_run()` 却返回 ``{"message": "立案提交成功（需根据实际网站完善逻辑）"}``。

BaseScraper 会据 `_run()` 没抛异常就把任务状态置为 ``SUCCESS``，
于是**律师看到「立案成功」而实际什么也没提交** —— 诉讼期限风险，是法律业务里
代价最高的一类错误。

真实立案实现在 ``plugins.court_automation.filing.playwright_filing.service.CourtZxfwFilingService``
（插件，私有子仓库）。本类只在插件不可用时被 ``scrapers/__init__.py`` 兜底导入，
所以它唯一的正确职责是：**立刻失败并说清原因**，绝不产出伪造的成功结果。

2026-10-28 审计修订：删除全部假实现，改为 fail-closed。
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseScraper

logger = logging.getLogger("apps.automation")

_PLUGIN_HINT = (
    "法院立案功能需要 plugins.court_automation 插件（私有子模块），当前环境未安装或导入失败。"
    "请确认："
    "1) backend/plugins 子模块已初始化（git submodule update --init backend/plugins）；"
    "2) 插件内 court_automation/filing/playwright_filing 可正常 import。"
    "在此之前立案任务无法执行——本占位实现不会假装成功。"
)


class CourtFilingScraper(BaseScraper):  # pragma: no cover
    """插件缺失时的兜底类：任何执行尝试都抛出明确错误（不伪造成功）。"""

    def _run(self) -> dict[str, Any]:
        """直接失败：没有真实立案实现时不允许产出成功结果。"""
        from apps.core.exceptions import BusinessException

        logger.error(
            "法院立案插件缺失，任务 %s 拒绝执行（fail-closed，不产出伪造成功）",
            getattr(self.task, "id", None),
        )
        raise BusinessException(
            message="法院立案插件未安装，无法执行立案",
            code="COURT_FILING_PLUGIN_MISSING",
            errors={"hint": _PLUGIN_HINT},
        )
