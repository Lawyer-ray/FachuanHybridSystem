"""测试 playwright-stealth 是否正常工作"""

import logging

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_stealth() -> None:
    """测试反检测效果"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()

        # 应用 playwright-stealth
        try:
            from playwright_stealth import Stealth

            stealth = Stealth()
            stealth.apply_stealth_sync(context)
            logger.info("✅ playwright-stealth 已应用")
        except ImportError:
            logger.error("❌ playwright-stealth 未安装")
            return

        page = context.new_page()

        # 访问检测网站
        logger.info("访问反爬虫检测网站...")
        page.goto("https://bot.sannysoft.com/", wait_until="networkidle")

        # 等待用户查看结果
        logger.info("请查看浏览器窗口，检查检测结果（绿色✅表示通过，红色❌表示被检测）")
        logger.info("按 Enter 键关闭浏览器...")
        input()

        browser.close()


if __name__ == "__main__":
    test_stealth()
