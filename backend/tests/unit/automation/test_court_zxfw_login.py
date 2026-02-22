"""
测试全国法院"一张网"登录功能
"""

import os
import sys

import django
import requests  # noqa: TID251

# 设置 Django 环境
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()

from playwright.sync_api import sync_playwright

from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService


def test_login():
    """测试登录功能"""
    print("=" * 60)
    print("测试全国法院'一张网'登录")
    print("=" * 60)

    # 1. 从 API 获取账号密码
    print("\n1. 获取账号密码...")
    try:
        response = requests.get("http://127.0.0.1:8002/api/v1/organization/credentials/1")  # noqa: S113
        response.raise_for_status()
        credential = response.json()

        account = credential["account"]
        password = credential["password"]

        print(f"   账号: {account}")
        print(f"   密码: {'*' * len(password)}")
    except Exception as e:
        print(f"   ❌ 获取账号密码失败: {e}")
        print("   请确保:")
        print("   - 后端服务已启动 (python manage.py runserver 0.0.0.0:8002)")
        print("   - 数据库中存在 ID=1 的凭证记录")
        return

    # 2. 启动浏览器
    print("\n2. 启动浏览器...")
    with sync_playwright() as p:
        # 使用有头模式，方便观察
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        page = context.new_page()

        print("   ✅ 浏览器已启动")

        # 3. 创建服务实例
        print("\n3. 创建服务实例...")
        service = CourtZxfwService(page, context)
        print("   ✅ 服务实例已创建")

        # 4. 执行登录
        print("\n4. 执行登录...")
        try:
            result = service.login(
                account=account,
                password=password,
                max_captcha_retries=5,  # 最多重试 5 次
                save_debug=True,  # 保存调试信息
            )

            print("\n" + "=" * 60)
            print("✅ 登录成功！")
            print("=" * 60)
            print(f"当前 URL: {result['url']}")
            print(f"Cookie 数量: {len(result['cookies'])}")

            # 等待用户观察
            input("\n按回车键继续...")

        except Exception as e:
            print("\n" + "=" * 60)
            print(f"❌ 登录失败: {e}")
            print("=" * 60)

            # 等待用户观察
            input("\n按回车键继续...")

        finally:
            browser.close()
            print("\n浏览器已关闭")


if __name__ == "__main__":
    test_login()
