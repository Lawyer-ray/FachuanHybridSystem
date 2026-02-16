#!/usr/bin/env python
"""
调试工具：查看页面结构
用于分析法院网站的页面结构，找到正确的选择器
"""
import sys

from playwright.sync_api import sync_playwright


def debug_page(url: str, headless: bool = False):
    """
    打开页面并保存 HTML 结构

    Args:
        url: 目标 URL
        headless: 是否无头模式
    """
    print(f"正在打开: {url}")
    print(f"模式: {'无头' if headless else '有头（可见浏览器）'}")
    print("=" * 60)

    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=headless, slow_mo=500 if not headless else 0)

        # 创建上下文
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )

        page = context.new_page()

        try:
            # 导航到页面
            print("正在加载页面...")
            page.goto(url, timeout=30000, wait_until="networkidle")
            print("✅ 页面加载完成")

            # 等待一下
            page.wait_for_timeout(3000)

            # 保存截图
            screenshot_path = "debug_screenshot.png"
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"✅ 截图已保存: {screenshot_path}")

            # 保存 HTML
            html_path = "debug_page.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())
            print(f"✅ HTML 已保存: {html_path}")

            # 分析页面元素
            print("\n" + "=" * 60)
            print("页面分析")
            print("=" * 60)

            # 查找按钮
            print("\n🔍 查找按钮:")
            buttons = page.locator("button").all()
            print(f"  找到 {len(buttons)} 个 <button> 元素")
            for i, btn in enumerate(buttons[:5]):  # 只显示前5个
                try:
                    text = btn.inner_text()
                    print(f"    {i+1}. {text}")
                except:
                    pass

            # 查找链接
            print("\n🔍 查找链接:")
            links = page.locator("a").all()
            print(f"  找到 {len(links)} 个 <a> 元素")
            for i, link in enumerate(links[:5]):  # 只显示前5个
                try:
                    text = link.inner_text()
                    href = link.get_attribute("href")
                    print(f"    {i+1}. {text} -> {href}")
                except:
                    pass

            # 查找包含"下载"的元素
            print("\n🔍 查找包含'下载'的元素:")
            download_elements = page.get_by_text("下载").all()
            print(f"  找到 {len(download_elements)} 个包含'下载'的元素")
            for i, elem in enumerate(download_elements):
                try:
                    tag = elem.evaluate("el => el.tagName")
                    text = elem.inner_text()
                    print(f"    {i+1}. <{tag}> {text}")
                except:
                    pass

            # 查找 ID 为 download 的元素
            print("\n🔍 查找 ID='download' 的元素:")
            download_ids = page.locator("#download").all()
            print(f"  找到 {len(download_ids)} 个 ID='download' 的元素")

            # 查找 ID 为 submit-btn 的元素
            print("\n🔍 查找 ID='submit-btn' 的元素:")
            submit_btns = page.locator("#submit-btn").all()
            print(f"  找到 {len(submit_btns)} 个 ID='submit-btn' 的元素")

            # 如果是有头模式，等待用户关闭
            if not headless:
                print("\n" + "=" * 60)
                print("浏览器窗口已打开，你可以手动查看页面")
                print("按 Enter 键关闭浏览器...")
                print("=" * 60)
                input()

        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback

            traceback.print_exc()

        finally:
            browser.close()
            print("\n✅ 浏览器已关闭")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="调试页面结构")
    parser.add_argument("url", help="目标 URL")
    parser.add_argument("--headless", action="store_true", help="无头模式")

    args = parser.parse_args()

    debug_page(args.url, args.headless)
