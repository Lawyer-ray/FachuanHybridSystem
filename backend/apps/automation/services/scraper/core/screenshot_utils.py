"""
截图工具类

纯工具方法，不包含业务逻辑
"""
import logging
from typing import List
from pathlib import Path
from django.conf import settings

logger = logging.getLogger("apps.automation")


class ScreenshotUtils:
    """截图相关工具方法"""
    
    @staticmethod
    def collect_screenshots(limit: int = 5) -> List[str]:
        """
        收集最新的截图
        
        Args:
            limit: 最多收集多少张
            
        Returns:
            截图 URL 列表
        """
        try:
            screenshot_dir = Path(settings.MEDIA_ROOT) / "automation" / "screenshots"
            if not screenshot_dir.exists():
                return []
            
            screenshots = sorted(
                screenshot_dir.glob("*.png"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            
            result = []
            for screenshot in screenshots[:limit]:
                relative_path = screenshot.relative_to(Path(settings.MEDIA_ROOT))
                screenshot_url = settings.MEDIA_URL + str(relative_path)
                result.append(screenshot_url)
            
            return result
        
        except Exception as e:
            logger.warning(f"收集截图失败: {e}")
            return []