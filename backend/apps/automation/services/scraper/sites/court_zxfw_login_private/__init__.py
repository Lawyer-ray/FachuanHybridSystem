"""
一张网 HTTP 直接登录插件（私有，不入 Git）

位置: backend/apps/automation/services/scraper/sites/court_zxfw_login_private/
作用: 通过纯 HTTP 请求完成法院一张网登录，无需启动 Playwright 浏览器
加密: SM2 国密（gmssl 库，C1C3C2 模式）
验证码: 复用项目已有的 ddddocr 识别器

部署方式:
    1. 将此目录放到 apps/automation/services/scraper/sites/ 下
    2. 安装依赖: uv add gmssl
    3. 无需任何配置，CourtZxfwService.login() 会自动检测并优先使用

不部署时:
    - CourtZxfwService.login() 自动回退到 Playwright 浏览器登录
    - 不影响任何现有功能
"""

from __future__ import annotations

import logging

logger = logging.getLogger("apps.automation")

_available = False
try:
    from .login_service import CourtZxfwHttpLoginService

    _available = True
except ImportError as e:
    logger.debug("HTTP 直接登录插件不可用: %s", e)

def is_available() -> bool:
    """插件是否可用（gmssl 已安装且模块完整）"""
    return _available

__all__ = ["CourtZxfwHttpLoginService", "is_available"]
