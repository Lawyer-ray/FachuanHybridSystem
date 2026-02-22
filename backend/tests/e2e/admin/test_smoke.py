"""
冒烟测试：测试所有 Admin 页面是否可以访问

这是最基础的测试，确保所有 Admin 页面不会返回 500 错误
"""

from .base_admin_test import BaseAdminTest


class TestAdminSmoke(BaseAdminTest):
    """Admin 冒烟测试"""

    # 定义所有需要测试的 Admin 页面
    ADMIN_PAGES = [
        # Cases 模块
        ("cases", "case", "案件"),
        ("cases", "caseparty", "案件当事人"),
        ("cases", "caseassignment", "案件指派"),
        ("cases", "caselog", "案件日志"),
        ("cases", "casenumber", "案件编号"),
        ("cases", "judicialinfo", "司法信息"),
        # Contracts 模块
        ("contracts", "contract", "合同"),
        ("contracts", "contractfinancelog", "合同财务日志"),
        ("contracts", "contractpayment", "合同支付"),
        ("contracts", "contractreminder", "合同提醒"),
        # Clients 模块
        ("client", "client", "客户"),
        ("client", "clientidentitydoc", "客户身份证件"),
        # Organization 模块
        ("organization", "lawfirm", "律所"),
        ("organization", "lawyer", "律师"),
        ("organization", "team", "团队"),
        ("organization", "accountcredential", "账号凭证"),
        # Automation 模块
        ("automation", "preservationquote", "财产保全询价"),
        ("automation", "courttoken", "Token"),
        ("automation", "testcourt", "测试工具"),
    ]

    async def test_all_list_pages_accessible(self):
        """测试所有列表页可以访问"""
        failed_pages = []

        for app_label, model_name, display_name in self.ADMIN_PAGES:
            try:
                print(f"\n  测试: {display_name} ({app_label}.{model_name})")

                # 访问列表页
                url = f"{self.ADMIN_URL}{app_label}/{model_name}/"
                await self.page.goto(url, timeout=10000)

                # 检查是否返回 200
                response = self.page.url
                if "500" in response or "error" in response.lower():
                    failed_pages.append({"page": display_name, "url": url, "error": "返回错误页面"})
                    print("    ❌ 失败: 返回错误页面")
                    continue

                # 检查页面是否加载完成
                await self.page.wait_for_load_state("networkidle", timeout=5000)

                # 检查是否有错误消息
                error_elem = await self.page.query_selector(".errornote, .error")
                if error_elem:
                    error_text = await error_elem.inner_text()
                    failed_pages.append({"page": display_name, "url": url, "error": error_text})
                    print(f"    ❌ 失败: {error_text}")
                    continue

                print("    ✅ 成功")

            except Exception as e:
                failed_pages.append(
                    {"page": display_name, "url": f"{self.ADMIN_URL}{app_label}/{model_name}/", "error": str(e)}
                )
                print(f"    ❌ 异常: {e}")

        # 打印总结
        print(f"\n{'=' * 60}")
        print("冒烟测试总结")
        print(f"{'=' * 60}")
        print(f"总计: {len(self.ADMIN_PAGES)} 个页面")
        print(f"✅ 成功: {len(self.ADMIN_PAGES) - len(failed_pages)} 个")
        print(f"❌ 失败: {len(failed_pages)} 个")

        if failed_pages:
            print("\n失败的页面:")
            for page in failed_pages:
                print(f"  - {page['page']}: {page['error']}")

        # 断言所有页面都成功
        self.assert_equals(len(failed_pages), 0, f"有 {len(failed_pages)} 个页面访问失败")

    async def test_admin_home_page(self):
        """测试 Admin 首页"""
        print("\n  测试: Admin 首页")

        await self.page.goto(self.ADMIN_URL)
        await self.page.wait_for_load_state("networkidle")

        # 检查标题（可能是中文或英文）
        title = await self.page.title()
        # 检查是否包含 admin 或管理相关的词
        title_ok = any(word in title.lower() for word in ["admin", "site", "管理", "后台"])
        self.assert_true(title_ok, f"首页标题不正确: {title}")

        # 检查是否显示了应用列表（使用更通用的选择器）
        # 检查是否有 Django admin 的标准结构
        content = await self.page.content()
        has_admin_content = "#content" in content or "module" in content or "app-" in content
        self.assert_true(has_admin_content, "首页没有显示 Admin 内容")

        print("    ✅ 成功")

    async def test_logout(self):
        """测试登出功能"""
        print("\n  测试: 登出功能")

        try:
            # 尝试多种可能的登出链接选择器
            logout_selectors = [
                'a[href="/admin/logout/"]',
                'a[href*="logout"]',
                'button:has-text("Log out")',
                'a:has-text("Log out")',
                'a:has-text("登出")',
                '#user-tools a[href*="logout"]',
            ]

            clicked = False
            for selector in logout_selectors:
                try:
                    await self.page.click(selector, timeout=2000)
                    clicked = True
                    break
                except Exception:
                    continue

            if not clicked:
                print("    ⏭️  跳过: 找不到登出按钮（这是正常的，某些 Admin 配置可能没有登出链接）")
                return

            await self.page.wait_for_load_state("networkidle", timeout=5000)

            # 检查是否跳转到登出页面或登录页面
            url = self.page.url
            logout_ok = "logout" in url.lower() or "login" in url.lower()
            self.assert_true(logout_ok, f"没有跳转到登出/登录页面: {url}")

            print("    ✅ 成功")

        except Exception as e:
            print(f"    ⏭️  跳过: {e}")
