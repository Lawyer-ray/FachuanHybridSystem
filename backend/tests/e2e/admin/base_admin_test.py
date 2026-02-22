"""
Admin 测试基类

提供通用的测试方法和工具
"""

import logging
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)


class BaseAdminTest:
    """Admin 测试基类"""

    ADMIN_URL = "http://localhost:8000/admin/"
    USERNAME = "法穿"
    PASSWORD = "test_password"

    playwright: Any = None
    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page  # set in setup()

    async def setup(self) -> None:
        """设置测试环境"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False, slow_mo=100
        )
        self.context = await self.browser.new_context(viewport={"width": 1920, "height": 1080})
        self.page = await self.context.new_page()

        # 登录
        await self.login()

    async def teardown(self) -> None:
        """清理测试环境"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def login(self) -> None:
        """登录 Admin"""
        logger.debug("登录 Admin...")
        await self.page.goto(self.ADMIN_URL)

        # 填写登录表单
        await self.page.fill('input[name="username"]', self.USERNAME)
        await self.page.fill('input[name="password"]', self.PASSWORD)
        await self.page.click('input[type="submit"]')

        # 等待登录成功（跳转到首页）
        await self.page.wait_for_url(f"{self.ADMIN_URL}**", timeout=10000)
        logger.info("登录成功")

    async def navigate_to_model(self, app_label: str, model_name: str) -> None:
        """导航到指定模型的列表页"""
        url = f"{self.ADMIN_URL}{app_label}/{model_name}/"
        logger.debug("访问 %s", url)
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

    async def click_add_button(self) -> None:
        """点击添加按钮（改进版 - 避免点击侧边栏链接）"""
        logger.debug("点击添加按钮")

        # 尝试多种可能的选择器，优先选择主内容区域的按钮
        selectors = [
            "#content a.addlink",
            ".object-tools a.addlink",
            "a.addlink:not(#nav-sidebar a)",
        ]

        for selector in selectors:
            try:
                await self.page.click(selector, timeout=3000)
                await self.page.wait_for_load_state("networkidle")
                logger.info("使用选择器: %s", selector)
                return
            except Exception:
                continue

        # 如果所有选择器都失败，直接导航到添加页面
        logger.debug("无法点击添加按钮，直接导航到添加页面")
        current_url = self.page.url
        add_url = current_url.rstrip("/") + "/add/"
        await self.page.goto(add_url)
        await self.page.wait_for_load_state("networkidle")

    async def fill_field(self, field_name: str, value: str) -> None:
        """填写表单字段（改进版，支持多种选择器和智能等待）"""
        # 如果是内联字段，先等待 JavaScript 初始化
        if "-0-" in field_name or "-1-" in field_name:
            field_base = field_name.split("-")[0]
            await self.wait_for_js_initialization(field_base)

            field_with_prefix: str | None = field_name.replace("-0-", "-__prefix__-").replace("-1-", "-__prefix__-")
        else:
            field_with_prefix = None

        # 尝试多种可能的选择器
        selectors = [
            f'input[name="{field_name}"]',
            f'textarea[name="{field_name}"]',
            f'input[id="id_{field_name}"]',
            f'textarea[id="id_{field_name}"]',
            f'input[name*="{field_name}"]',
            f'textarea[name*="{field_name}"]',
        ]

        if field_with_prefix:
            selectors.extend(
                [
                    f'input[name="{field_with_prefix}"]',
                    f'textarea[name="{field_with_prefix}"]',
                ]
            )

        for selector in selectors:
            try:
                await self.page.wait_for_selector(selector, timeout=2000)
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        await element.fill(value, timeout=5000)
                        logger.info("填写字段: %s = %s", field_name, value)
                        return
            except Exception:
                continue

        await self.debug_page_structure(f"field_{field_name}_not_found.html")
        logger.warning("尝试的选择器: %s", selectors)
        raise Exception(f"无法找到字段: {field_name}，尝试了选择器: {selectors}")

    async def select_option(self, field_name: str, value: str) -> None:
        """选择下拉框选项（改进版，支持智能等待）"""
        if "-0-" in field_name or "-1-" in field_name:
            field_base = field_name.split("-")[0]
            await self.wait_for_js_initialization(field_base)

            field_with_prefix: str | None = field_name.replace("-0-", "-__prefix__-").replace("-1-", "-__prefix__-")
        else:
            field_with_prefix = None

        selectors = [
            f'select[name="{field_name}"]',
            f'select[id="id_{field_name}"]',
            f'select[name*="{field_name}"]',
        ]

        if field_with_prefix:
            selectors.extend(
                [
                    f'select[name="{field_with_prefix}"]',
                ]
            )

        for selector in selectors:
            try:
                await self.page.wait_for_selector(selector, timeout=2000)
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        await element.select_option(value, timeout=5000)
                        logger.info("选择选项: %s = %s", field_name, value)
                        return
            except Exception:
                continue

        await self.debug_page_structure(f"select_{field_name}_not_found.html")
        raise Exception(f"无法找到下拉框: {field_name}，尝试了选择器: {selectors}")

    async def submit_form(self, button_name: str = "_save") -> None:
        """提交表单"""
        logger.debug("提交表单")
        await self.page.click(f'input[name="{button_name}"]')
        await self.page.wait_for_load_state("networkidle")

    async def check_success_message(self) -> bool:
        """检查成功消息"""
        success_msg = await self.page.query_selector(".success, .messagelist .success")
        return success_msg is not None

    async def check_error_message(self) -> bool:
        """检查错误消息"""
        error_msg = await self.page.query_selector(".errorlist, .errornote")
        return error_msg is not None

    async def get_error_text(self) -> str:
        """获取错误消息文本"""
        error_elem = await self.page.query_selector(".errorlist, .errornote")
        if error_elem:
            return await error_elem.inner_text()
        return ""

    async def check_page_title(self, expected_text: str) -> bool:
        """检查页面标题"""
        title = await self.page.title()
        return expected_text in title

    async def check_element_exists(self, selector: str) -> bool:
        """检查元素是否存在"""
        element = await self.page.query_selector(selector)
        return element is not None

    async def get_table_row_count(self) -> int:
        """获取列表表格的行数"""
        rows = await self.page.query_selector_all("#result_list tbody tr")
        return len(rows)

    async def click_first_edit_link(self) -> None:
        """点击第一条记录的编辑链接"""
        logger.debug("点击第一条记录的编辑链接")
        await self.page.click("#result_list tbody tr:first-child th a")
        await self.page.wait_for_load_state("networkidle")

    async def click_delete_button(self) -> None:
        """点击删除按钮"""
        logger.debug("点击删除按钮")
        await self.page.click("a.deletelink")
        await self.page.wait_for_load_state("networkidle")

    async def confirm_delete(self) -> None:
        """确认删除"""
        logger.debug("确认删除")
        await self.page.click('input[type="submit"]')
        await self.page.wait_for_load_state("networkidle")

    async def add_inline_row(self, inline_prefix: str) -> None:
        """添加内联表单行（支持 django-nested-admin）"""
        logger.debug("添加内联行: %s", inline_prefix)

        prefix_mapping = {
            "caseparty_set": "parties",
            "caseassignment_set": "assignments",
            "supervisingauthority_set": "supervising_authorities",
            "casenumber_set": "case_numbers",
            "caselog_set": "logs",
            "caselogattachment_set": "attachments",
            "accountcredential_set": "credentials",
            "clientidentitydoc_set": "identity_docs",
            "cases": "cases",
        }

        actual_prefix = prefix_mapping.get(inline_prefix, inline_prefix)

        total_forms_before: str | None = None
        try:
            total_forms_input = await self.page.query_selector(f'input[name="{actual_prefix}-TOTAL_FORMS"]')
            if total_forms_input:
                total_forms_before = await total_forms_input.get_attribute("value")
                logger.debug("添加前 TOTAL_FORMS: %s", total_forms_before)
        except Exception:
            pass

        original_model_name = inline_prefix.replace("_set", "")

        add_button_selectors = [
            f".djn-add-handler.djn-model-cases-{original_model_name}",
            f"#{actual_prefix}-group .add-handler.djn-add-handler",
            f'[id*="{actual_prefix}"] .add-handler.djn-add-handler',
            ".add-handler.djn-add-handler",
            f"#{inline_prefix}-group .add-row a",
            f".{inline_prefix} .add-row a",
            f".inline-group.{inline_prefix} .add-row a",
            f"#{actual_prefix}-group .add-row a",
            ".add-row a",
        ]

        for selector in add_button_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        await element.click(timeout=5000)
                        logger.info("使用选择器: %s", selector)

                        if total_forms_before is not None:
                            try:
                                for i in range(10):
                                    await self.page.wait_for_timeout(500)
                                    total_forms_input = await self.page.query_selector(
                                        f'input[name="{actual_prefix}-TOTAL_FORMS"]'
                                    )
                                    if total_forms_input:
                                        current_value = await total_forms_input.get_attribute("value")
                                        if current_value and int(current_value) > int(total_forms_before):
                                            logger.info(
                                                "新行已创建 (TOTAL_FORMS: %s → %s)",
                                                total_forms_before,
                                                current_value,
                                            )
                                            break
                            except Exception as e:
                                logger.warning("等待TOTAL_FORMS增加失败: %s", e)

                        await self.page.wait_for_timeout(2000)
                        return
            except Exception as e:
                logger.warning("选择器失败: %s - %s", selector, e)
                continue

        await self.debug_page_structure(f"inline_{inline_prefix}_failed.html")
        await self.take_screenshot(f"inline_{inline_prefix}_failed")
        raise Exception(f"无法找到内联添加按钮: {inline_prefix} (实际: {actual_prefix})")

    async def take_screenshot(self, name: str) -> None:
        """截图（改进版 - 避免超时）"""
        import os
        from pathlib import Path

        screenshot_dir = Path("backend/tests/admin/screenshots")
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        try:
            await self.page.screenshot(path=str(screenshot_dir / f"{name}.png"), timeout=10000)
            logger.info("截图已保存: %s.png", name)
        except Exception as e:
            logger.warning("截图失败: %s", e)
            try:
                await self.page.screenshot(path=str(screenshot_dir / f"{name}.png"), timeout=5000)
                logger.info("截图已保存（第二次尝试）: %s.png", name)
            except Exception:
                logger.error("截图完全失败")

    async def debug_page_structure(self, filename: str = "page_structure.html") -> None:
        """保存页面 HTML 结构用于调试"""
        from pathlib import Path

        debug_dir = Path("backend/tests/admin/debug")
        debug_dir.mkdir(parents=True, exist_ok=True)
        try:
            content = await self.page.content()
            (debug_dir / filename).write_text(content, encoding="utf-8")
            logger.info("调试 HTML 已保存: %s", filename)
        except Exception as e:
            logger.warning("保存调试 HTML 失败: %s", e)

    async def wait_for_inline_to_load(self, inline_prefix: str, timeout: int = 5000) -> None:
        """等待内联表单加载完成"""
        try:
            await self.page.wait_for_selector(f'[id*="{inline_prefix}"]', timeout=timeout)
            await self.page.wait_for_timeout(500)
        except Exception:
            logger.warning("等待内联加载超时: %s", inline_prefix)

    async def wait_for_js_initialization(self, field_pattern: str, timeout: int = 8000) -> None:
        """等待 JavaScript 初始化完成，将 __prefix__ 替换为实际索引"""
        try:
            await self.page.wait_for_selector(
                f'[name*="{field_pattern}"][name*="-0-"]:not([name*="__prefix__"]):visible',
                timeout=timeout,
                state="visible",
            )
            logger.info("JavaScript 初始化完成: %s", field_pattern)
        except Exception:
            logger.warning("JavaScript 初始化超时: %s，继续尝试", field_pattern)
            await self.page.wait_for_timeout(2000)

    def get_inline_field_name(self, inline_prefix: str, row_index: int, field_name: str) -> str:
        """获取内联字段的实际名称"""
        prefix_mapping = {
            "caseparty_set": "parties",
            "caseassignment_set": "assignments",
            "supervisingauthority_set": "supervising_authorities",
            "casenumber_set": "case_numbers",
            "caselog_set": "logs",
            "caselogattachment_set": "attachments",
            "accountcredential_set": "accountcredential_set",
            "clientidentitydoc_set": "identity_docs",
            "cases": "cases",
        }

        actual_prefix = prefix_mapping.get(inline_prefix, inline_prefix)
        return f"{actual_prefix}-{row_index}-{field_name}"

    async def fill_raw_id_field(self, field_name: str, value: str) -> None:
        """填写 raw_id_fields（外键输入框）"""
        selectors = [
            f'input[name="{field_name}"]',
            f'input[id="id_{field_name}"]',
        ]

        for selector in selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        await element.fill(value, timeout=5000)
                        return
            except Exception:
                continue

        raise Exception(f"无法找到 raw_id 字段: {field_name}")

    async def select_radio_button(self, field_name: str, value: str) -> None:
        """选择 radio button"""
        selector = f'input[name="{field_name}"][value="{value}"]'

        try:
            await self.page.wait_for_selector(selector, timeout=5000)
            element = await self.page.query_selector(selector)
            if element:
                await element.check(timeout=5000)
                logger.info("选择 radio: %s = %s", field_name, value)
                return
        except Exception:
            pass

        raise Exception(f"无法找到 radio button: {field_name}={value}")

    async def fill_field_smart(self, field_name: str, value: str) -> None:
        """智能填写字段（自动检测类型并选择最佳方法）"""
        logger.debug("智能填写字段: %s = %s", field_name, value)

        methods: list[tuple[str, Any]] = [
            ("select", self.select_option),
            ("input", self.fill_field),
            ("raw_id", self.fill_raw_id_field),
            ("radio", self.select_radio_button),
        ]

        for method_name, method in methods:
            try:
                await method(field_name, value)
                return
            except Exception:
                logger.warning("%s 方法失败", method_name)
                continue

        await self.debug_page_structure(f"smart_fill_{field_name}_failed.html")
        raise Exception(f"无法填写字段 {field_name}，所有方法都失败")

    async def measure_page_load_time(self, url: str) -> float:
        """测量页面加载时间"""
        import time

        start = time.time()
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")
        end = time.time()
        return end - start

    async def search(self, query: str) -> None:
        """使用搜索功能"""
        logger.debug("搜索: %s", query)
        await self.page.fill('input[name="q"]', query)
        await self.page.click('input[type="submit"][value="Search"]')
        await self.page.wait_for_load_state("networkidle")

    async def apply_filter(self, filter_name: str, filter_value: str) -> None:
        """应用过滤器"""
        logger.debug("应用过滤器: %s=%s", filter_name, filter_value)
        await self.page.click(f'#changelist-filter a[href*="{filter_name}={filter_value}"]')
        await self.page.wait_for_load_state("networkidle")

    async def select_action(self, action_name: str) -> None:
        """选择 Admin Action"""
        logger.debug("选择 Action: %s", action_name)
        await self.page.select_option('select[name="action"]', action_name)

    async def select_all_rows(self) -> None:
        """选择所有行"""
        logger.debug("选择所有行")
        await self.page.click("#action-toggle")

    async def execute_action(self) -> None:
        """执行 Action"""
        logger.debug("执行 Action")
        await self.page.click('button[name="index"]')
        await self.page.wait_for_load_state("networkidle")

    def assert_true(self, condition: bool, message: str = "") -> None:
        """断言为真"""
        if not condition:
            raise AssertionError(message or "断言失败")

    def assert_false(self, condition: bool, message: str = "") -> None:
        """断言为假"""
        if condition:
            raise AssertionError(message or "断言失败")

    def assert_equals(self, actual: Any, expected: Any, message: str = "") -> None:
        """断言相等"""
        if actual != expected:
            raise AssertionError(message or f"期望 {expected}，实际 {actual}")

    def assert_contains(self, text: str, substring: str, message: str = "") -> None:
        """断言包含"""
        if substring not in text:
            raise AssertionError(message or f"'{text}' 不包含 '{substring}'")

    # ========== 验证错误检测方法 ==========

    async def check_validation_error(
        self, field_name: str | None = None, expected_message: str | None = None
    ) -> bool:
        """
        检查验证错误

        Args:
            field_name: 字段名（可选），如果指定则只检查该字段的错误
            expected_message: 期望的错误消息（可选），如果指定则检查消息内容

        Returns:
            是否检测到验证错误
        """
        logger.debug("检查验证错误%s", f" (字段: {field_name})" if field_name else "")

        error_selectors = [
            ".errorlist li",
            ".errors",
            ".field-error",
            ".inline-errors",
            '[class*="error"]',
            ".djn-error",
            ".errornote",
        ]

        if field_name:
            field_error_selectors = [
                f"#{field_name} + .errorlist",
                f'[name="{field_name}"] + .errorlist',
                f".field-{field_name} .errorlist",
                f'[id*="{field_name}"] .errorlist',
            ]
            error_selectors = field_error_selectors + error_selectors

        for selector in error_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                if elements:
                    for element in elements:
                        is_visible = await element.is_visible()
                        if is_visible:
                            error_text = (await element.inner_text()).strip()
                            if error_text:
                                if expected_message:
                                    if expected_message in error_text:
                                        logger.info("检测到验证错误: %s", error_text)
                                        return True
                                else:
                                    logger.info("检测到验证错误: %s", error_text)
                                    return True
            except Exception:
                continue

        logger.debug("未检测到验证错误")
        return False

    async def get_validation_errors(self) -> list[dict[str, str]]:
        """
        获取所有验证错误

        Returns:
            错误列表，每个错误包含 'field', 'message', 'location'
        """
        logger.debug("获取所有验证错误")

        errors: list[dict[str, str]] = []

        error_selectors = [
            (".errorlist li", "main_form"),
            (".errors", "main_form"),
            (".field-error", "main_form"),
            (".inline-errors", "inline"),
            (".djn-error", "inline"),
            (".errornote", "main_form"),
        ]

        for selector, location in error_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                for element in elements:
                    is_visible = await element.is_visible()
                    if is_visible:
                        error_text = (await element.inner_text()).strip()
                        if error_text:
                            field_name = await self._find_error_field(element)
                            errors.append(
                                {"field": field_name or "unknown", "message": error_text, "location": location}
                            )
            except Exception:
                continue

        if errors:
            logger.info("找到 %d 个验证错误", len(errors))
            for error in errors:
                logger.debug("  - %s: %s", error["field"], error["message"])
        else:
            logger.debug("未找到验证错误")

        return errors

    async def verify_no_validation_errors(self) -> bool:
        """
        验证没有验证错误

        Returns:
            是否没有错误（True = 没有错误，False = 有错误）
        """
        logger.debug("验证没有验证错误")

        errors = await self.get_validation_errors()

        if not errors:
            logger.info("确认没有验证错误")
            return True
        else:
            logger.error("发现 %d 个验证错误", len(errors))
            return False

    async def _find_error_field(self, error_element: Any) -> str | None:
        """
        尝试找到错误消息关联的字段名

        Args:
            error_element: 错误元素

        Returns:
            字段名（如果找到）
        """
        try:
            parent = await error_element.evaluate_handle("el => el.parentElement")

            field = await parent.query_selector("input, select, textarea")
            if field:
                field_name = await field.get_attribute("name")
                if field_name:
                    return field_name  # type: ignore[no-any-return]

            parent_class = await parent.get_attribute("class")
            if parent_class and "field-" in parent_class:
                for cls in parent_class.split():
                    if cls.startswith("field-"):
                        return cls.replace("field-", "")  # type: ignore[no-any-return]

            parent_id = await parent.get_attribute("id")
            if parent_id:
                return parent_id  # type: ignore[no-any-return]
        except Exception:
            pass

        return None

    async def wait_for_validation_error(self, timeout: int = 5000, field_name: str | None = None) -> bool:
        """
        等待验证错误消息出现（支持动态加载）

        Args:
            timeout: 超时时间（毫秒）
            field_name: 字段名（可选），如果指定则只等待该字段的错误

        Returns:
            是否检测到验证错误
        """
        logger.debug("等待验证错误出现%s", f" (字段: {field_name})" if field_name else "")

        error_selectors = [
            ".errorlist li",
            ".errors",
            ".field-error",
            ".inline-errors",
            '[class*="error"]',
            ".djn-error",
            ".errornote",
        ]

        if field_name:
            field_error_selectors = [
                f"#{field_name} + .errorlist",
                f'[name="{field_name}"] + .errorlist',
                f".field-{field_name} .errorlist",
                f'[id*="{field_name}"] .errorlist',
            ]
            error_selectors = field_error_selectors + error_selectors

        for selector in error_selectors:
            try:
                await self.page.wait_for_selector(selector, timeout=timeout, state="visible")
                logger.info("检测到验证错误 (选择器: %s)", selector)
                return True
            except Exception:
                continue

        logger.debug("超时未检测到验证错误")
        return False

    async def fix_validation_error(
        self,
        field_name: str,
        correct_value: str,
        is_inline: bool = False,
        inline_prefix: str | None = None,
        row_index: int | None = None,
    ) -> None:
        """
        修正验证错误

        Args:
            field_name: 字段名
            correct_value: 正确的值
            is_inline: 是否是内联表单字段
            inline_prefix: 内联表单前缀（如果是内联字段）
            row_index: 内联行索引（如果是内联字段）
        """
        logger.debug("修正验证错误: %s = %s", field_name, correct_value)

        if is_inline and inline_prefix is not None and row_index is not None:
            full_field_name = self.get_inline_field_name(inline_prefix, row_index, field_name)
        else:
            full_field_name = field_name

        try:
            await self.fill_field_smart(full_field_name, correct_value)
            logger.info("字段已修正")
        except Exception as e:
            logger.warning("修正失败: %s", e)
            try:
                await self.fill_field(full_field_name, correct_value)
                logger.info("字段已修正（使用 fill_field）")
            except Exception as e2:
                logger.error("修正失败: %s", e2)
                raise
