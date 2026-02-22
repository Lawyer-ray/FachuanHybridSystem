#!/usr/bin/env python
"""
测试两个具体链接的下载功能

链接1: https://sd.gdems.com/v3/dzsd/B0MBNG
  - 先点击"确定并预览材料"
  - 然后点击 /html/body/div/div[1]/div[1]/label/a/img 下载压缩包

链接2: https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?...
  - 左边是文书列表，右边是 PDF 预览窗口
  - 下载按钮在 iframe 内部
  - XPath: /html/body/div[1]/div[2]/div[5]/div/div[1]/div[2]/button[4]
"""
import json
import os
import sys
import time
from datetime import datetime

import pytest

from apps.core.path import Path

if os.getenv("RUN_EXTERNAL_DOWNLOAD_TESTS") != "1":
    pytest.skip(
        "external download tests disabled (set RUN_EXTERNAL_DOWNLOAD_TESTS=1 to enable)", allow_module_level=True
    )

# 设置路径
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
api_system_dir = os.path.join(backend_dir, "apiSystem")
sys.path.insert(0, api_system_dir)
sys.path.insert(0, backend_dir)

# 设置 Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
import django

django.setup()

from django.conf import settings
from playwright.sync_api import sync_playwright

# 测试配置
TEST_LINKS = {
    "gdems": {
        "url": "https://sd.gdems.com/v3/dzsd/B0MBNG",
        "description": "广东电子送达 - 需要先点击确认按钮",
        "confirm_button_xpath": None,  # 先点击"确定并预览材料"
        "download_xpath": "/html/body/div/div[1]/div[1]/label/a/img",
    },
    "zxfw": {
        "url": "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=cdfe234627e648e790fdeb2628fb4e01&sdbh=bc241560b2a347608c42b334d24bae03&sdsin=a1eaef1ff793b238a4d53dd069277765",
        "description": "法院执行文书送达 - 单文件下载",
        "download_xpath": "/html/body/div[1]/div[2]/div[5]/div/div[1]/div[2]/button[4]",
        "has_iframe": True,
    },
    "zxfw_multi": {
        "url": "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=95d15d23d671468e99204442d404021a&sdbh=c6913b2c177847c3a7bd3aaca8aa08d4&sdsin=ce810a6098854dd863a1b567638ba91e",
        "description": "法院执行文书送达 - 多文件下载",
        "has_iframe": True,
        "multi_file": True,
    },
}


def create_download_dir():
    """创建下载目录"""
    download_dir = (
        Path(settings.MEDIA_ROOT) / "automation" / "test_downloads" / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


def save_page_state(page, download_dir: Path, name: str):
    """保存页面状态用于调试"""
    # 截图
    screenshot_path = download_dir / f"{name}_screenshot.png"
    page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"  📸 截图已保存: {screenshot_path}")

    # HTML
    html_path = download_dir / f"{name}_page.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(page.content())
    print(f"  📄 HTML已保存: {html_path}")

    return screenshot_path, html_path


def analyze_page(page, download_dir: Path, name: str): # noqa: C901
    """分析页面元素"""
    analysis = {
        "url": page.url,
        "title": page.title(),
        "buttons": [],
        "links": [],
        "iframes": [],
        "images": [],
    }

    # 分析按钮
    try:
        buttons = page.locator("button").all()
        for i, btn in enumerate(buttons[:20]):
            try:
                analysis["buttons"].append(
                    {
                        "index": i,
                        "text": btn.inner_text()[:100] if btn.inner_text() else "",
                        "visible": btn.is_visible(),
                        "enabled": btn.is_enabled(),
                    }
                )
            except Exception:
                pass
    except Exception:
        pass

    # 分析链接
    try:
        links = page.locator("a").all()
        for i, link in enumerate(links[:20]):
            try:
                analysis["links"].append(
                    {
                        "index": i,
                        "text": link.inner_text()[:100] if link.inner_text() else "",
                        "href": link.get_attribute("href")[:200] if link.get_attribute("href") else "",
                        "visible": link.is_visible(),
                    }
                )
            except Exception:
                pass
    except Exception:
        pass

    # 分析 iframe
    try:
        iframes = page.locator("iframe").all()
        for i, iframe in enumerate(iframes):
            try:
                analysis["iframes"].append(
                    {
                        "index": i,
                        "src": iframe.get_attribute("src")[:200] if iframe.get_attribute("src") else "",
                        "name": iframe.get_attribute("name") or "",
                    }
                )
            except Exception:
                pass
    except Exception:
        pass

    # 分析图片（可能是下载图标）
    try:
        images = page.locator("img").all()
        for i, img in enumerate(images[:20]):
            try:
                analysis["images"].append(
                    {
                        "index": i,
                        "src": img.get_attribute("src")[:200] if img.get_attribute("src") else "",
                        "alt": img.get_attribute("alt") or "",
                        "visible": img.is_visible(),
                    }
                )
            except Exception:
                pass
    except Exception:
        pass

    # 保存分析结果
    analysis_path = download_dir / f"{name}_analysis.json"
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"  📊 分析已保存: {analysis_path}")

    return analysis


def test_gdems_download(download_dir: Path): # noqa: C901
    """测试 sd.gdems.com 下载"""
    print("\n" + "=" * 70)
    print("🔗 测试 sd.gdems.com 下载")
    print("=" * 70)

    config = TEST_LINKS["gdems"]
    url = config["url"]  # type: ignore[index]
    print(f"URL: {url}")

    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(
            headless=False, args=["--no-sandbox", "--disable-setuid-sandbox"]  # 显示浏览器窗口便于调试
        )

        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},
        )

        page = context.new_page()

        try:
            # 1. 导航到页面
            print("\n📍 步骤1: 导航到页面...")
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(3)

            save_page_state(page, download_dir, "gdems_1_initial")
            analysis = analyze_page(page, download_dir, "gdems_1_initial")

            print(f"  页面标题: {analysis['title']}")
            print(f"  按钮数量: {len(analysis['buttons'])}")
            print(f"  链接数量: {len(analysis['links'])}")

            # 2. 点击"确定并预览材料"按钮
            print("\n📍 步骤2: 点击'确定并预览材料'按钮...")

            # 尝试多种方式找到确认按钮
            confirm_button = None

            # 方式1: 通过文本
            try:
                confirm_button = page.get_by_text("确认并预览材料", exact=False)
                if confirm_button.count() > 0 and confirm_button.first.is_visible():
                    print("  ✓ 通过文本找到确认按钮")
                else:
                    confirm_button = None
            except Exception:
                pass

            # 方式2: 通过按钮文本
            if not confirm_button:
                try:
                    confirm_button = page.locator(
                        "button:has-text('确认'), button:has-text('确定'), button:has-text('预览')"
                    )
                    if confirm_button.count() > 0 and confirm_button.first.is_visible():
                        print("  ✓ 通过按钮选择器找到确认按钮")
                    else:
                        confirm_button = None
                except Exception:
                    pass

            # 方式3: 通过 ID
            if not confirm_button:
                try:
                    confirm_button = page.locator("#submit-btn, #confirm-btn, .submit-btn, .confirm-btn")
                    if confirm_button.count() > 0 and confirm_button.first.is_visible():
                        print("  ✓ 通过 ID/class 找到确认按钮")
                    else:
                        confirm_button = None
                except Exception:
                    pass

            if confirm_button and confirm_button.count() > 0:
                confirm_button.first.click()
                print("  ✓ 已点击确认按钮")

                # 等待页面加载
                page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(5)

                save_page_state(page, download_dir, "gdems_2_after_confirm")
                analysis = analyze_page(page, download_dir, "gdems_2_after_confirm")
            else:
                print("  ⚠️ 未找到确认按钮，可能页面已经在预览状态")

            # 3. 点击下载按钮
            print("\n📍 步骤3: 点击下载按钮...")

            download_xpath = config["download_xpath"]  # type: ignore[index]
            download_button = None

            # 方式1: 使用提供的 XPath
            try:
                download_button = page.locator(f"xpath={download_xpath}")
                if download_button.count() > 0 and download_button.first.is_visible():
                    print(f"  ✓ 通过 XPath 找到下载按钮: {download_xpath}")
                else:
                    download_button = None
            except Exception as e:
                print(f"  XPath 查找失败: {e}")

            # 方式2: 查找包含下载图标的链接
            if not download_button:
                try:
                    # 查找 label 下的 a 标签（包含 img）
                    download_button = page.locator("label a:has(img)")
                    if download_button.count() > 0 and download_button.first.is_visible():
                        print("  ✓ 通过 label a:has(img) 找到下载按钮")
                    else:
                        download_button = None
                except Exception:
                    pass

            # 方式3: 查找任何包含"下载"的元素
            if not download_button:
                try:
                    download_button = page.locator("a:has-text('下载'), button:has-text('下载'), [title*='下载']")
                    if download_button.count() > 0 and download_button.first.is_visible():
                        print("  ✓ 通过文本找到下载按钮")
                    else:
                        download_button = None
                except Exception:
                    pass

            if download_button and download_button.count() > 0:
                # 滚动到元素
                download_button.first.scroll_into_view_if_needed()
                time.sleep(1)

                # 监听下载
                with page.expect_download(timeout=60000) as download_info:
                    download_button.first.click()
                    print("  ✓ 已点击下载按钮，等待下载...")

                download = download_info.value

                # 保存文件
                filename = download.suggested_filename or "download.zip"
                filepath = download_dir / filename
                download.save_as(str(filepath))

                print("\n✅ 下载成功！")
                print(f"  文件名: {filename}")
                print(f"  保存路径: {filepath}")
                print(f"  文件大小: {os.path.getsize(filepath)} bytes")

                return True, str(filepath)
            else:
                print("  ❌ 未找到下载按钮")
                save_page_state(page, download_dir, "gdems_3_no_download_button")
                return False, None

        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback

            traceback.print_exc()
            save_page_state(page, download_dir, "gdems_error")
            return False, None
        finally:
            browser.close()


def test_zxfw_download(download_dir: Path): # noqa: C901
    """测试 zxfw.court.gov.cn 下载"""
    print("\n" + "=" * 70)
    print("🔗 测试 zxfw.court.gov.cn 下载")
    print("=" * 70)

    config = TEST_LINKS["zxfw"]
    url = config["url"]  # type: ignore[index]
    print(f"URL: {url[:80]}...")

    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=False, args=["--no-sandbox", "--disable-setuid-sandbox"])

        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},
        )

        page = context.new_page()

        try:
            # 1. 导航到页面
            print("\n📍 步骤1: 导航到页面...")
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(5)  # 等待 JS 渲染

            save_page_state(page, download_dir, "zxfw_1_initial")
            analysis = analyze_page(page, download_dir, "zxfw_1_initial")

            print(f"  页面标题: {analysis['title']}")
            print(f"  iframe 数量: {len(analysis['iframes'])}")

            # 打印 iframe 信息
            for i, iframe_info in enumerate(analysis["iframes"]):
                print(f"  iframe {i}: {iframe_info['src'][:80]}...")

            # 2. 切换到 iframe
            print("\n📍 步骤2: 切换到 iframe...")

            # 查找包含 PDF viewer 的 iframe
            frame = None

            iframes = page.locator("iframe").all()
            for i, iframe in enumerate(iframes):
                src = iframe.get_attribute("src") or ""
                print(f"  检查 iframe {i}: {src[:60]}...")

                if "pdfjs" in src or "viewer" in src:
                    # 使用 frame_locator 获取 frame
                    frame = page.frame_locator(f"iframe >> nth={i}")
                    print("  ✓ 找到 PDF viewer iframe")
                    break

            if not frame:
                # 如果没找到特定的，尝试第一个 iframe
                if iframes:
                    frame = page.frame_locator("iframe >> nth=0")
                    print("  使用第一个 iframe")

            if frame:
                # 等待 iframe 加载
                time.sleep(3)

                # 在 iframe 内分析
                print("\n📍 步骤3: 在 iframe 内查找下载按钮...")

                # 查找下载按钮
                download_xpath = config["download_xpath"]  # type: ignore[index]
                download_button = None

                # 方式1: 使用提供的 XPath
                try:
                    download_button = frame.locator(f"xpath={download_xpath}")
                    # frame_locator 不支持 count()，直接尝试
                    print(f"  尝试 XPath: {download_xpath}")
                except Exception as e:
                    print(f"  XPath 查找失败: {e}")
                    download_button = None

                # 方式2: 查找 PDF.js 的下载按钮
                if not download_button:
                    try:
                        # PDF.js 通常有 id="download" 的按钮
                        download_button = frame.locator(
                            "#download, #downloadButton, button[title*='下载'], button[title*='Download']"
                        )
                        print("  尝试 PDF.js 选择器")
                    except Exception:
                        pass

                # 方式3: 查找工具栏中的按钮
                if not download_button:
                    try:
                        # 查找工具栏区域的按钮
                        download_button = frame.locator(".toolbar button, #toolbarContainer button")
                        print("  尝试工具栏选择器")
                    except Exception:
                        pass

                # 尝试点击下载按钮
                try:
                    # 先尝试 XPath
                    btn = frame.locator(f"xpath={download_xpath}")
                    btn.first.wait_for(state="visible", timeout=10000)
                    btn.first.scroll_into_view_if_needed()
                    time.sleep(1)

                    # 监听下载
                    with page.expect_download(timeout=60000) as download_info:
                        btn.first.click()
                        print("  ✓ 已点击下载按钮，等待下载...")

                    download = download_info.value

                    # 保存文件
                    filename = download.suggested_filename or "document.pdf"
                    filepath = download_dir / filename
                    download.save_as(str(filepath))

                    print("\n✅ 下载成功！")
                    print(f"  文件名: {filename}")
                    print(f"  保存路径: {filepath}")
                    print(f"  文件大小: {os.path.getsize(filepath)} bytes")

                    return True, str(filepath)

                except Exception as e:
                    print(f"  XPath 方式失败: {e}")

                    # 尝试 PDF.js 下载按钮
                    try:
                        btn = frame.locator("#download")
                        btn.first.wait_for(state="visible", timeout=5000)

                        with page.expect_download(timeout=60000) as download_info:
                            btn.first.click()
                            print("  ✓ 通过 #download 点击下载按钮")

                        download = download_info.value
                        filename = download.suggested_filename or "document.pdf"
                        filepath = download_dir / filename
                        download.save_as(str(filepath))

                        print("\n✅ 下载成功！")
                        print(f"  文件名: {filename}")
                        print(f"  保存路径: {filepath}")
                        print(f"  文件大小: {os.path.getsize(filepath)} bytes")

                        return True, str(filepath)

                    except Exception as e2:
                        print(f"  #download 方式也失败: {e2}")

                        # 打印 iframe 内所有按钮
                        print("\n  iframe 内的所有按钮:")
                        try:
                            all_buttons = frame.locator("button").all()
                            for i, btn in enumerate(all_buttons[:15]):
                                try:
                                    title = btn.get_attribute("title") or ""
                                    text = btn.inner_text()[:30] if btn.inner_text() else ""
                                    print(f"    {i}: title='{title}', text='{text}'")
                                except Exception:
                                    pass
                        except Exception as e3:
                            print(f"  无法列出按钮: {e3}")

                        return False, None
            else:
                print("  ❌ 未找到 iframe")
                return False, None

        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback

            traceback.print_exc()
            save_page_state(page, download_dir, "zxfw_error")
            return False, None
        finally:
            browser.close()


def test_zxfw_multi_download(download_dir: Path): # noqa: C901
    """测试 zxfw.court.gov.cn 多文件下载"""
    print("\n" + "=" * 70)
    print("🔗 测试 zxfw.court.gov.cn 多文件下载")
    print("=" * 70)

    config = TEST_LINKS["zxfw_multi"]
    url = config["url"]  # type: ignore[index]
    print(f"URL: {url[:80]}...")

    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=False, args=["--no-sandbox", "--disable-setuid-sandbox"])

        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},
        )

        page = context.new_page()
        downloaded_files = []

        try:
            # 1. 导航到页面
            print("\n📍 步骤1: 导航到页面...")
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(5)  # 等待 JS 渲染

            save_page_state(page, download_dir, "zxfw_multi_1_initial")
            analysis = analyze_page(page, download_dir, "zxfw_multi_1_initial")

            print(f"  页面标题: {analysis['title']}")
            print(f"  iframe 数量: {len(analysis['iframes'])}")

            # 2. 检测文书列表数量
            print("\n📍 步骤2: 检测文书列表...")

            doc_list_xpath = "/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view/uni-view[1]/uni-view[1]/uni-view" # noqa: E501

            try:
                doc_items = page.locator(f"xpath={doc_list_xpath}").all()
                doc_count = len(doc_items)
                print(f"  检测到 {doc_count} 个文书项")
            except Exception as e:
                print(f"  无法检测文书列表: {e}")
                doc_count = 1

            if doc_count == 0:
                doc_count = 1

            # 3. 逐一下载每个文书
            for doc_index in range(1, doc_count + 1):
                print(f"\n📍 步骤3.{doc_index}: 下载第 {doc_index}/{doc_count} 个文书...")

                try:
                    # 点击文书项（如果有多个）
                    if doc_count > 1:
                        doc_item_xpath = f"/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view/uni-view[1]/uni-view[1]/uni-view[{doc_index}]" # noqa: E501

                        try:
                            doc_item = page.locator(f"xpath={doc_item_xpath}")
                            if doc_item.count() > 0:
                                doc_item.first.click()
                                print(f"  ✓ 已点击第 {doc_index} 个文书项")
                                time.sleep(3)  # 等待 PDF 加载
                        except Exception as e:
                            print(f"  点击文书项失败: {e}")

                    # 查找 iframe
                    frame = None
                    try:
                        frame = page.frame_locator("#if")
                        print("  ✓ 通过 #if 找到 iframe")
                    except Exception:
                        # 备用方式
                        iframes = page.locator("iframe").all()
                        for i, iframe in enumerate(iframes):
                            src = iframe.get_attribute("src") or ""
                            iframe_id = iframe.get_attribute("id") or ""
                            if iframe_id == "if" or "pdfjs" in src:
                                frame = page.frame_locator(f"iframe >> nth={i}")
                                print(f"  ✓ 找到 iframe (index {i})")
                                break

                    if not frame:
                        print(f"  ❌ 第 {doc_index} 个文书未找到 iframe")
                        continue

                    # 点击下载按钮
                    try:
                        btn = frame.locator("#download")
                        btn.first.wait_for(state="visible", timeout=10000)
                        btn.first.scroll_into_view_if_needed()
                        time.sleep(1)

                        with page.expect_download(timeout=60000) as download_info:
                            btn.first.click()
                            print(f"  ✓ 已点击第 {doc_index} 个文书的下载按钮")

                        download = download_info.value
                        filename = download.suggested_filename or f"document_{doc_index}.pdf"
                        filepath = download_dir / filename
                        download.save_as(str(filepath))

                        print(f"  ✓ 文件已保存: {filename} ({os.path.getsize(filepath)} bytes)")
                        downloaded_files.append(str(filepath))

                    except Exception as e:
                        print(f"  ❌ 第 {doc_index} 个文书下载失败: {e}")

                    time.sleep(1)

                except Exception as e:
                    print(f"  ❌ 处理第 {doc_index} 个文书时出错: {e}")

            if downloaded_files:
                print(f"\n✅ 下载完成！共下载 {len(downloaded_files)}/{doc_count} 个文件")
                for f in downloaded_files:
                    print(f"  - {f}")
                return True, downloaded_files
            else:
                print("\n❌ 没有成功下载任何文件")
                return False, None

        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback

            traceback.print_exc()
            save_page_state(page, download_dir, "zxfw_multi_error")
            return False, None
        finally:
            browser.close()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="法院文书下载测试")
    parser.add_argument("--type", choices=["gdems", "zxfw", "zxfw_multi", "all"], default="all", help="测试类型")
    args = parser.parse_args()

    print("=" * 70)
    print("🧪 法院文书下载测试")
    print("=" * 70)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试类型: {args.type}")

    # 创建下载目录
    download_dir = create_download_dir()
    print(f"下载目录: {download_dir}")

    results = []

    # 测试 gdems
    if args.type in ["gdems", "all"]:
        success, filepath = test_gdems_download(download_dir)
        results.append(("sd.gdems.com", success, filepath))

    # 测试 zxfw 单文件
    if args.type in ["zxfw", "all"]:
        success, filepath = test_zxfw_download(download_dir)
        results.append(("zxfw.court.gov.cn (单文件)", success, filepath))

    # 测试 zxfw 多文件
    if args.type in ["zxfw_multi", "all"]:
        success, files = test_zxfw_multi_download(download_dir)
        results.append(("zxfw.court.gov.cn (多文件)", success, files))

    # 打印总结
    print("\n" + "=" * 70)
    print("📊 测试总结")
    print("=" * 70)

    all_passed = True
    for name, success, filepath in results:
        status = "✅ 成功" if success else "❌ 失败"
        print(f"  {name}: {status}")
        if filepath:
            if isinstance(filepath, list):
                for f in filepath:
                    print(f"    - {f}")
            else:
                print(f"    文件: {filepath}")
        if not success:
            all_passed = False

    print(f"\n下载目录: {download_dir}")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
