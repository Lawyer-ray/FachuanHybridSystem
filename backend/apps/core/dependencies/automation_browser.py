"""浏览器自动化相关依赖注入."""

from typing import Any


def get_anti_detection() -> Any:
    """获取反检测模块实例"""
    from apps.automation.services.scraper.core.anti_detection import anti_detection

    return anti_detection


def create_court_zxfw_service(*, page: Any, context: Any, site_name: str = "court_zxfw") -> Any:
    """创建法院一张网服务实例"""
    from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService

    return CourtZxfwService(page=page, context=context, site_name=site_name)
