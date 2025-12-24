#!/usr/bin/env python
"""
快速测试爬虫 - 直接运行，不通过 Django-Q
"""
import os
import sys

# 设置 Django 环境
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'apiSystem'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.settings')

import django
django.setup()

from apps.automation.models import ScraperTask, ScraperTaskType
from apps.automation.services.scraper.scrapers import CourtDocumentScraper

def test_gdems():
    """测试 sd.gdems.com"""
    print("=" * 60)
    print("测试 sd.gdems.com")
    print("=" * 60)
    
    url = "https://sd.gdems.com/v3/dzsd/B0MBNGh"
    
    task = ScraperTask.objects.create(
        task_type=ScraperTaskType.COURT_DOCUMENT,
        url=url,
        priority=5,
        config={}
    )
    
    print(f"任务 ID: {task.id}")
    print(f"URL: {url}")
    
    try:
        scraper = CourtDocumentScraper(task)
        result = scraper.execute()
        print("\n✅ 成功!")
        print(f"结果: {result}")
        return True
    except Exception as e:
        print(f"\n❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_zxfw():
    """测试 zxfw.court.gov.cn"""
    print("\n" + "=" * 60)
    print("测试 zxfw.court.gov.cn")
    print("=" * 60)
    
    url = "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=cdfe234627e648e790fdeb2628fb4e01&sdbh=bc241560b2a347608c42b334d24bae03&sdsin=a1eaef1ff793b238a4d53dd069277765"
    
    task = ScraperTask.objects.create(
        task_type=ScraperTaskType.COURT_DOCUMENT,
        url=url,
        priority=5,
        config={}
    )
    
    print(f"任务 ID: {task.id}")
    print(f"URL: {url[:80]}...")
    
    try:
        scraper = CourtDocumentScraper(task)
        result = scraper.execute()
        print("\n✅ 成功!")
        print(f"结果: {result}")
        return True
    except Exception as e:
        print(f"\n❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=["gdems", "zxfw", "all"], default="all")
    args = parser.parse_args()
    
    if args.type in ["gdems", "all"]:
        test_gdems()
    
    if args.type in ["zxfw", "all"]:
        test_zxfw()
    
    print("\n测试完成!")
