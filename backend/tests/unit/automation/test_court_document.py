#!/usr/bin/env python
"""
测试法院文书下载爬虫

使用方法:
    python test_court_document.py                    # 测试所有
    python test_court_document.py --type zxfw        # 只测试 zxfw
    python test_court_document.py --type gdems       # 只测试 gdems
    python test_court_document.py --url "链接"       # 测试自定义链接
    python test_court_document.py --debug            # 启用详细调试
    python test_court_document.py --interactive      # 交互式模式（暂停等待）
"""
import argparse
import logging
import os
import sys

import django
import pytest

pytestmark = pytest.mark.skip(reason="集成脚本，不作为单元测试运行")

# 设置 Django 环境
# 注意：从 tests 目录运行时，需要正确设置路径
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
api_system_dir = os.path.join(backend_dir, "apiSystem")
sys.path.insert(0, api_system_dir)
sys.path.insert(0, backend_dir)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()

from apps.automation.models import ScraperTask, ScraperTaskType
from apps.automation.services.scraper.scrapers import CourtDocumentScraper

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 设置 automation 日志器为 DEBUG
automation_logger = logging.getLogger("apps.automation")
automation_logger.setLevel(logging.DEBUG)


def print_separator(title: str = ""):
    """打印分隔线"""
    print("\n" + "=" * 70)
    if title:
        print(f"  {title}")
        print("=" * 70)


def print_result(result: dict):
    """格式化打印结果"""
    print("\n📊 执行结果:")
    print("-" * 50)
    for key, value in result.items():
        if isinstance(value, list):
            print(f"  {key}:")
            for item in value:
                print(f"    - {item}")
        elif isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")


@pytest.mark.django_db
def test_zxfw_court(url=None, interactive=False):
    """测试 zxfw.court.gov.cn 链接"""
    print_separator("测试 zxfw.court.gov.cn 文书下载")

    if not url:
        url = "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=28938b642114470e80472ca62d5f622b&sdbh=97e29694bd324242bf4d50d00284e473&sdsin=83b0c4f5d938757e11b2cfd0292a1e31"

    print(f"🔗 URL: {url[:80]}...")

    # 创建测试任务
    task = ScraperTask.objects.create(task_type=ScraperTaskType.COURT_DOCUMENT, url=url, priority=5, config={})

    print(f"📋 任务 ID: {task.id}")
    print("\n⏳ 开始执行爬虫...")

    if interactive:
        input("\n按 Enter 键开始执行（浏览器窗口将打开）...")

    try:
        # 执行爬虫
        scraper = CourtDocumentScraper(task)
        result = scraper.execute()

        print_separator("✅ 下载成功！")
        print_result(result)

        # 显示文件位置
        print("\n📁 文件位置:")
        for f in result.get("files", []):
            print(f"  ✓ {f}")

        return True

    except Exception as e:
        print_separator("❌ 下载失败")
        print(f"\n错误: {e}")

        import traceback

        print("\n详细错误信息:")
        traceback.print_exc()

        # 显示调试提示
        print("\n" + "=" * 70)
        print("💡 调试提示:")
        print("=" * 70)
        print("1. 检查截图文件:")
        print(f"   ls -la {os.path.join(backend_dir, 'apiSystem/media/automation/screenshots/')}")
        print("\n2. 检查调试文件:")
        print(f"   ls -la {os.path.join(backend_dir, 'apiSystem/media/automation/downloads/')}")
        print("\n3. 查看页面分析 JSON:")
        print("   cat *_analysis.json")
        print("\n4. 使用交互式模式:")
        print("   python test_court_document.py --type zxfw --interactive")

        if interactive:
            input("\n按 Enter 键继续...")

        return False


@pytest.mark.django_db
def test_gdems(url=None, interactive=False):
    """测试 sd.gdems.com 链接"""
    print_separator("测试 sd.gdems.com 文书下载")

    if not url:
        url = "https://sd.gdems.com/v3/dzsd/B0MBNG"  # 修正 URL

    print(f"🔗 URL: {url}")

    # 创建测试任务
    task = ScraperTask.objects.create(task_type=ScraperTaskType.COURT_DOCUMENT, url=url, priority=5, config={})

    print(f"📋 任务 ID: {task.id}")
    print("\n⏳ 开始执行爬虫...")

    if interactive:
        input("\n按 Enter 键开始执行（浏览器窗口将打开）...")

    try:
        # 执行爬虫
        scraper = CourtDocumentScraper(task)
        result = scraper.execute()

        print_separator("✅ 下载成功！")
        print_result(result)

        return True

    except Exception as e:
        print_separator("❌ 下载失败")
        print(f"\n错误: {e}")

        import traceback

        print("\n详细错误信息:")
        traceback.print_exc()

        if interactive:
            input("\n按 Enter 键继续...")

        return False


def main():
    parser = argparse.ArgumentParser(
        description="测试法院文书下载爬虫",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python test_court_document.py                     # 测试所有类型
  python test_court_document.py --type zxfw         # 只测试 zxfw
  python test_court_document.py --type gdems        # 只测试 gdems
  python test_court_document.py --url "你的链接"    # 测试自定义链接
  python test_court_document.py --debug             # 启用详细调试
  python test_court_document.py --interactive       # 交互式模式
        """,
    )
    parser.add_argument("--type", choices=["zxfw", "gdems", "all"], default="all", help="测试类型 (默认: all)")
    parser.add_argument("--url", type=str, help="自定义测试链接")
    parser.add_argument("--debug", action="store_true", help="启用详细调试日志")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互式模式（每步暂停等待确认）")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        automation_logger.setLevel(logging.DEBUG)
        print("🔧 调试模式已启用")

    print_separator("法院文书下载爬虫测试")
    print(f"测试类型: {args.type}")
    print(f"调试模式: {'是' if args.debug else '否'}")
    print(f"交互模式: {'是' if args.interactive else '否'}")
    if args.url:
        print(f"自定义链接: {args.url}")

    results = []

    # 根据类型执行测试
    if args.type in ["zxfw", "all"]:
        url = args.url if args.type == "zxfw" else None
        success = test_zxfw_court(url, args.interactive)
        results.append(("zxfw.court.gov.cn", success))

    if args.type in ["gdems", "all"]:
        url = args.url if args.type == "gdems" else None
        success = test_gdems(url, args.interactive)
        results.append(("sd.gdems.com", success))

    # 显示总结
    print_separator("测试总结")
    all_passed = True
    for name, success in results:
        status = "✅ 成功" if success else "❌ 失败"
        print(f"  {name}: {status}")
        if not success:
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 所有测试通过！")
    else:
        print("⚠️ 部分测试失败，请查看上方的调试提示")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
