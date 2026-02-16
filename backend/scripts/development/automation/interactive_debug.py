#!/usr/bin/env python
"""
交互式调试工具

在浏览器中打开页面，手动分析页面结构，找到正确的选择器。

使用方法:
    python interactive_debug.py "https://zxfw.court.gov.cn/..."
    python interactive_debug.py "https://sd.gdems.com/..."
"""
import json
import logging
import sys

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


def analyze_page(page) -> dict:
    """分析页面元素"""
    analysis = {
        "url": page.url,
        "title": page.title(),
        "buttons": [],
        "links": [],
        "download_elements": [],
        "clickable_elements": [],
    }

    # 分析按钮
    logger.info("\n🔍 分析按钮...")
    buttons = page.locator("button").all()
    logger.info("   找到 %d 个按钮", len(buttons))
    for i, btn in enumerate(buttons[:15]):
        try:
            text = btn.inner_text()[:40] if btn.inner_text() else "(无文本)"
            visible = btn.is_visible()
            if visible:
                analysis["buttons"].append({"index": i, "text": text})
                logger.info("   [%d] %s", i, text)
        except:
            pass

    # 分析链接
    logger.info("\n🔍 分析链接...")
    links = page.locator("a").all()
    logger.info("   找到 %d 个链接", len(links))
    for i, link in enumerate(links[:15]):
        try:
            text = link.inner_text()[:40] if link.inner_text() else "(无文本)"
            href = link.get_attribute("href")[:60] if link.get_attribute("href") else ""
            visible = link.is_visible()
            if visible and text.strip():
                analysis["links"].append({"index": i, "text": text, "href": href})
                logger.info("   [%d] %s -> %s", i, text, href)
        except:
            pass

    # 分析包含"下载"的元素
    logger.info("\n🔍 分析包含'下载'的元素...")
    download_elements = page.locator('*:has-text("下载")').all()
    logger.info("   找到 %d 个包含'下载'的元素", len(download_elements))
    for i, elem in enumerate(download_elements[:10]):
        try:
            tag = elem.evaluate("el => el.tagName")
            text = elem.inner_text()[:40] if elem.inner_text() else ""
            visible = elem.is_visible()
            if visible:
                analysis["download_elements"].append({"index": i, "tag": tag, "text": text})
                logger.info("   [%d] <%s> %s", i, tag, text)
        except:
            pass

    # 分析可点击元素
    logger.info("\n🔍 分析可点击元素...")
    clickable = page.locator("button, a, [onclick], [role='button'], input[type='submit']").all()
    logger.info("   找到 %d 个可点击元素", len(clickable))
    for i, elem in enumerate(clickable[:20]):
        try:
            tag = elem.evaluate("el => el.tagName")
            text = elem.inner_text()[:30] if elem.inner_text() else "(无文本)"
            visible = elem.is_visible()
            if visible:
                analysis["clickable_elements"].append({"index": i, "tag": tag, "text": text})
        except:
            pass

    return analysis


def interactive_session(url: str):
    """交互式调试会话"""
    logger.info("=" * 70)
    logger.info("🔧 交互式调试工具")
    logger.info("=" * 70)
    logger.info("\n目标 URL: %s", url)

    with sync_playwright() as p:
        # 启动浏览器（有头模式）
        logger.info("\n⏳ 启动浏览器...")
        browser = p.chromium.launch(
            headless=False,
            slow_mo=500,
        )

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )

        page = context.new_page()

        try:
            # 导航到页面
            logger.info("\n⏳ 导航到: %s", url)
            page.goto(url, timeout=30000, wait_until="networkidle")
            logger.info("✅ 页面加载完成")

            # 等待额外时间
            logger.info("⏳ 等待 5 秒让页面完全渲染...")
            page.wait_for_timeout(5000)

            while True:
                logger.info("\n" + "=" * 70)
                logger.info("📋 命令菜单:")
                logger.info("=" * 70)
                logger.info("  1. 分析页面元素")
                logger.info("  2. 保存截图")
                logger.info("  3. 保存 HTML")
                logger.info("  4. 尝试点击下载按钮")
                logger.info("  5. 执行自定义 JavaScript")
                logger.info("  6. 刷新页面")
                logger.info("  7. 等待 N 秒")
                logger.info("  8. 查看当前 URL")
                logger.info("  9. 退出")
                logger.info("-" * 70)

                choice = input("请选择 (1-9): ").strip()

                if choice == "1":
                    analysis = analyze_page(page)
                    # 保存分析结果
                    with open("page_analysis.json", "w", encoding="utf-8") as f:
                        json.dump(analysis, f, ensure_ascii=False, indent=2)
                    logger.info("\n✅ 分析结果已保存到 page_analysis.json")

                elif choice == "2":
                    filename = input("截图文件名 (默认: screenshot.png): ").strip() or "screenshot.png"
                    page.screenshot(path=filename, full_page=True)
                    logger.info("✅ 截图已保存: %s", filename)

                elif choice == "3":
                    filename = input("HTML 文件名 (默认: page.html): ").strip() or "page.html"
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(page.content())
                    logger.info("✅ HTML 已保存: %s", filename)

                elif choice == "4":
                    logger.info("\n尝试点击下载按钮...")
                    selectors = [
                        "#download",
                        "text=下载",
                        "button:has-text('下载')",
                        "a:has-text('下载')",
                    ]

                    for selector in selectors:
                        try:
                            elem = page.locator(selector).first
                            if elem.count() > 0 and elem.is_visible():
                                logger.info("  找到元素: %s", selector)
                                confirm = input("  是否点击? (y/n): ").strip().lower()
                                if confirm == "y":
                                    try:
                                        with page.expect_download(timeout=30000) as download_info:
                                            elem.click()
                                        download = download_info.value
                                        logger.info("  ✅ 下载成功: %s", download.suggested_filename)
                                        download.save_as(download.suggested_filename)
                                    except Exception as e:
                                        logger.error("  ❌ 下载失败: %s", e)
                                break
                        except:
                            pass
                    else:
                        logger.warning("  ❌ 未找到下载按钮")

                elif choice == "5":
                    js_code = input("输入 JavaScript 代码: ").strip()
                    if js_code:
                        try:
                            result = page.evaluate(js_code)
                            logger.info("执行结果: %s", result)
                        except Exception as e:
                            logger.error("执行错误: %s", e)

                elif choice == "6":
                    logger.info("刷新页面...")
                    page.reload(wait_until="networkidle")
                    logger.info("✅ 页面已刷新")

                elif choice == "7":
                    seconds = input("等待秒数: ").strip()
                    try:
                        page.wait_for_timeout(int(seconds) * 1000)
                        logger.info("✅ 已等待 %s 秒", seconds)
                    except:
                        logger.error("❌ 无效的秒数")

                elif choice == "8":
                    logger.info("\n当前 URL: %s", page.url)
                    logger.info("页面标题: %s", page.title())

                elif choice == "9":
                    logger.info("\n👋 退出调试工具")
                    break

                else:
                    logger.warning("❌ 无效的选择")

        except Exception as e:
            logger.error("\n❌ 错误: %s", e)
            import traceback

            traceback.print_exc()

        finally:
            logger.info("\n关闭浏览器...")
            browser.close()


def main():
    if len(sys.argv) < 2:
        logger.info("使用方法: python interactive_debug.py <URL>")
        logger.info("\n示例:")
        logger.info("  python interactive_debug.py 'https://zxfw.court.gov.cn/...'")
        logger.info("  python interactive_debug.py 'https://sd.gdems.com/v3/dzsd/xxx'")
        sys.exit(1)

    url = sys.argv[1]
    interactive_session(url)


if __name__ == "__main__":
    main()
