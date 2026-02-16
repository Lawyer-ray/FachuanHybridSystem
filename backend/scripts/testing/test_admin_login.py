"""
测试 Django Admin 登录
使用 Playwright 自动化测试
"""

import asyncio

from playwright.async_api import async_playwright


async def test_admin_login():
    """测试 Django Admin 登录"""
    admin_url = "http://localhost:8000/admin/"
    username = "法穿"
    password = "1234qwer"

    async with async_playwright() as p:
        # 启动浏览器（使用 headless=False 可以看到浏览器操作）
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print(f"🌐 访问 Django Admin: {admin_url}")
            await page.goto(admin_url, wait_until="networkidle")

            # 等待登录表单加载
            await page.wait_for_selector('input[name="username"]', timeout=5000)
            print("✅ 登录页面加载成功")

            # 填写用户名
            print(f"📝 填写用户名: {username}")
            await page.fill('input[name="username"]', username)

            # 填写密码
            print(f"🔑 填写密码: {'*' * len(password)}")
            await page.fill('input[name="password"]', password)

            # 点击登录按钮
            print("🖱️  点击登录按钮")
            await page.click('input[type="submit"]')

            # 等待页面跳转
            await page.wait_for_load_state("networkidle")

            # 检查是否登录成功
            current_url = page.url
            print(f"📍 当前 URL: {current_url}")

            # 检查是否有登录成功的标志
            if "/admin/" in current_url and "login" not in current_url:
                print("✅ 登录成功！")

                # 截图保存
                screenshot_path = "backend/logs/admin_login_success.png"
                await page.screenshot(path=screenshot_path)
                print(f"📸 截图已保存: {screenshot_path}")

                # 获取页面标题
                title = await page.title()
                print(f"📄 页面标题: {title}")

                # 检查是否有用户信息显示
                try:
                    user_tools = await page.query_selector("#user-tools")
                    if user_tools:
                        user_text = await user_tools.inner_text()
                        print(f"👤 用户信息: {user_text}")
                except:
                    pass

                return True
            else:
                print("❌ 登录失败")

                # 检查是否有错误信息
                try:
                    error_msg = await page.query_selector(".errornote")
                    if error_msg:
                        error_text = await error_msg.inner_text()
                        print(f"⚠️  错误信息: {error_text}")
                except:
                    pass

                # 截图保存
                screenshot_path = "backend/logs/admin_login_failed.png"
                await page.screenshot(path=screenshot_path)
                print(f"📸 截图已保存: {screenshot_path}")

                return False

        except Exception as e:
            print(f"❌ 测试过程中出现错误: {str(e)}")

            # 保存错误截图
            try:
                screenshot_path = "backend/logs/admin_login_error.png"
                await page.screenshot(path=screenshot_path)
                print(f"📸 错误截图已保存: {screenshot_path}")
            except:
                pass

            return False

        finally:
            # 等待几秒钟以便观察
            print("⏳ 等待 3 秒...")
            await asyncio.sleep(3)

            # 关闭浏览器
            await browser.close()
            print("🔚 浏览器已关闭")


if __name__ == "__main__":
    print("=" * 60)
    print("Django Admin 登录测试")
    print("=" * 60)

    result = asyncio.run(test_admin_login())

    print("=" * 60)
    if result:
        print("✅ 测试通过")
    else:
        print("❌ 测试失败")
    print("=" * 60)
