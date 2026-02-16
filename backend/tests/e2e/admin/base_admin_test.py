"""
Admin 测试基类

提供通用的测试方法和工具
"""
import asyncio
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Page, Browser, BrowserContext


class BaseAdminTest:
    """Admin 测试基类"""
    
    ADMIN_URL = "http://localhost:8000/admin/"
    USERNAME = "法穿"
    PASSWORD = "test_password"
    
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
    
    async def setup(self):
        """设置测试环境"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,  # 显示浏览器，方便调试
            slow_mo=100  # 减慢操作速度，方便观察
        )
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        self.page = await self.context.new_page()
        
        # 登录
        await self.login()
    
    async def teardown(self):
        """清理测试环境"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def login(self):
        """登录 Admin"""
        print(f"  → 登录 Admin...")
        await self.page.goto(self.ADMIN_URL)
        
        # 填写登录表单
        await self.page.fill('input[name="username"]', self.USERNAME)
        await self.page.fill('input[name="password"]', self.PASSWORD)
        await self.page.click('input[type="submit"]')
        
        # 等待登录成功（跳转到首页）
        await self.page.wait_for_url(f"{self.ADMIN_URL}**", timeout=10000)
        print(f"  ✓ 登录成功")
    
    async def navigate_to_model(self, app_label: str, model_name: str):
        """导航到指定模型的列表页"""
        url = f"{self.ADMIN_URL}{app_label}/{model_name}/"
        print(f"  → 访问 {url}")
        await self.page.goto(url)
        await self.page.wait_for_load_state('networkidle')
    
    async def click_add_button(self):
        """点击添加按钮（改进版 - 避免点击侧边栏链接）"""
        print(f"  → 点击添加按钮")
        
        # 尝试多种可能的选择器，优先选择主内容区域的按钮
        selectors = [
            '#content a.addlink',  # 主内容区域的添加按钮
            '.object-tools a.addlink',  # 对象工具栏的添加按钮
            'a.addlink:not(#nav-sidebar a)',  # 不在侧边栏的添加按钮
        ]
        
        for selector in selectors:
            try:
                await self.page.click(selector, timeout=3000)
                await self.page.wait_for_load_state('networkidle')
                print(f"  ✓ 使用选择器: {selector}")
                return
            except:
                continue
        
        # 如果所有选择器都失败，直接导航到添加页面
        print(f"  ℹ️  无法点击添加按钮，直接导航到添加页面")
        current_url = self.page.url
        add_url = current_url.rstrip('/') + '/add/'
        await self.page.goto(add_url)
        await self.page.wait_for_load_state('networkidle')
    
    async def fill_field(self, field_name: str, value: str):
        """填写表单字段（改进版，支持多种选择器和智能等待）"""
        # 如果是内联字段，先等待 JavaScript 初始化
        if '-0-' in field_name or '-1-' in field_name:
            field_base = field_name.split('-')[0]
            await self.wait_for_js_initialization(field_base)
            
            # 如果JavaScript还没初始化，尝试使用__prefix__
            field_with_prefix = field_name.replace('-0-', '-__prefix__-').replace('-1-', '-__prefix__-')
        else:
            field_with_prefix = None
        
        # 尝试多种可能的选择器
        selectors = [
            f'input[name="{field_name}"]',
            f'textarea[name="{field_name}"]',
            f'input[id="id_{field_name}"]',
            f'textarea[id="id_{field_name}"]',
            # 支持内联字段
            f'input[name*="{field_name}"]',
            f'textarea[name*="{field_name}"]',
        ]
        
        # 如果有__prefix__版本，也尝试
        if field_with_prefix:
            selectors.extend([
                f'input[name="{field_with_prefix}"]',
                f'textarea[name="{field_with_prefix}"]',
            ])
        
        for selector in selectors:
            try:
                # 等待元素出现
                await self.page.wait_for_selector(selector, timeout=2000)
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        await element.fill(value, timeout=5000)
                        print(f"    ✓ 填写字段: {field_name} = {value}")
                        return
            except Exception as e:
                continue
        
        # 如果所有选择器都失败，保存调试信息
        await self.debug_page_structure(f"field_{field_name}_not_found.html")
        print(f"    ⚠️  尝试的选择器: {selectors}")
        raise Exception(f"无法找到字段: {field_name}，尝试了选择器: {selectors}")
    
    async def select_option(self, field_name: str, value: str):
        """选择下拉框选项（改进版，支持智能等待）"""
        # 如果是内联字段，先等待 JavaScript 初始化
        if '-0-' in field_name or '-1-' in field_name:
            field_base = field_name.split('-')[0]
            await self.wait_for_js_initialization(field_base)
            
            # 如果JavaScript还没初始化，尝试使用__prefix__
            field_with_prefix = field_name.replace('-0-', '-__prefix__-').replace('-1-', '-__prefix__-')
        else:
            field_with_prefix = None
        
        selectors = [
            f'select[name="{field_name}"]',
            f'select[id="id_{field_name}"]',
            # 支持内联字段
            f'select[name*="{field_name}"]',
        ]
        
        # 如果有__prefix__版本，也尝试
        if field_with_prefix:
            selectors.extend([
                f'select[name="{field_with_prefix}"]',
            ])
        
        for selector in selectors:
            try:
                # 等待元素出现
                await self.page.wait_for_selector(selector, timeout=2000)
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        await element.select_option(value, timeout=5000)
                        print(f"    ✓ 选择选项: {field_name} = {value}")
                        return
            except Exception as e:
                continue
        
        # 如果所有选择器都失败，保存调试信息
        await self.debug_page_structure(f"select_{field_name}_not_found.html")
        raise Exception(f"无法找到下拉框: {field_name}，尝试了选择器: {selectors}")
    
    async def submit_form(self, button_name: str = "_save"):
        """提交表单"""
        print(f"  → 提交表单")
        await self.page.click(f'input[name="{button_name}"]')
        await self.page.wait_for_load_state('networkidle')
    
    async def check_success_message(self) -> bool:
        """检查成功消息"""
        success_msg = await self.page.query_selector('.success, .messagelist .success')
        return success_msg is not None
    
    async def check_error_message(self) -> bool:
        """检查错误消息"""
        error_msg = await self.page.query_selector('.errorlist, .errornote')
        return error_msg is not None
    
    async def get_error_text(self) -> str:
        """获取错误消息文本"""
        error_elem = await self.page.query_selector('.errorlist, .errornote')
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
        rows = await self.page.query_selector_all('#result_list tbody tr')
        return len(rows)
    
    async def click_first_edit_link(self):
        """点击第一条记录的编辑链接"""
        print(f"  → 点击第一条记录的编辑链接")
        await self.page.click('#result_list tbody tr:first-child th a')
        await self.page.wait_for_load_state('networkidle')
    
    async def click_delete_button(self):
        """点击删除按钮"""
        print(f"  → 点击删除按钮")
        await self.page.click('a.deletelink')
        await self.page.wait_for_load_state('networkidle')
    
    async def confirm_delete(self):
        """确认删除"""
        print(f"  → 确认删除")
        await self.page.click('input[type="submit"]')
        await self.page.wait_for_load_state('networkidle')
    
    async def add_inline_row(self, inline_prefix: str):
        """添加内联表单行（支持 django-nested-admin）"""
        print(f"  → 添加内联行: {inline_prefix}")
        
        # 映射：从 Django 标准命名到 nested-admin 命名
        prefix_mapping = {
            'caseparty_set': 'parties',
            'caseassignment_set': 'assignments',
            'supervisingauthority_set': 'supervising_authorities',
            'casenumber_set': 'case_numbers',
            'caselog_set': 'logs',
            'caselogattachment_set': 'attachments',
            'accountcredential_set': 'credentials',  # 律师凭证使用nested-admin命名
            'clientidentitydoc_set': 'identity_docs',
            'cases': 'cases',
        }
        
        # 获取实际的 prefix
        actual_prefix = prefix_mapping.get(inline_prefix, inline_prefix)
        
        # 获取添加前的TOTAL_FORMS值
        total_forms_before = None
        try:
            total_forms_input = await self.page.query_selector(f'input[name="{actual_prefix}-TOTAL_FORMS"]')
            if total_forms_input:
                total_forms_before = await total_forms_input.get_attribute('value')
                print(f"    ℹ️  添加前 TOTAL_FORMS: {total_forms_before}")
        except:
            pass
        
        # 查找添加按钮（支持多种格式）
        # 对于django-nested-admin，类名使用原始模型名（如caselog），不是映射后的名字（如logs）
        original_model_name = inline_prefix.replace('_set', '')  # caselog_set -> caselog
        
        add_button_selectors = [
            # django-nested-admin 格式（最具体的选择器优先）
            f'.djn-add-handler.djn-model-cases-{original_model_name}',  # 如 .djn-add-handler.djn-model-cases-caselog
            f'#{actual_prefix}-group .add-handler.djn-add-handler',
            f'[id*="{actual_prefix}"] .add-handler.djn-add-handler',
            '.add-handler.djn-add-handler',
            
            # 标准 Django Admin 格式
            f'#{inline_prefix}-group .add-row a',
            f'.{inline_prefix} .add-row a',
            f'.inline-group.{inline_prefix} .add-row a',
            
            # 通用格式
            f'#{actual_prefix}-group .add-row a',
            '.add-row a',
        ]
        
        for selector in add_button_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    # 检查元素是否可见
                    is_visible = await element.is_visible()
                    if is_visible:
                        await element.click(timeout=5000)
                        print(f"    ✓ 使用选择器: {selector}")
                        
                        # 等待TOTAL_FORMS值增加（说明新行已创建）
                        if total_forms_before is not None:
                            try:
                                # 使用简单的轮询等待
                                for i in range(10):  # 最多等待5秒
                                    await self.page.wait_for_timeout(500)
                                    total_forms_input = await self.page.query_selector(f'input[name="{actual_prefix}-TOTAL_FORMS"]')
                                    if total_forms_input:
                                        current_value = await total_forms_input.get_attribute('value')
                                        if current_value and int(current_value) > int(total_forms_before):
                                            print(f"    ✓ 新行已创建 (TOTAL_FORMS: {total_forms_before} → {current_value})")
                                            break
                            except Exception as e:
                                print(f"    ⚠️  等待TOTAL_FORMS增加失败: {e}")
                        
                        # 额外等待确保JavaScript完成
                        await self.page.wait_for_timeout(2000)
                        return
            except Exception as e:
                print(f"    ⚠️  选择器失败: {selector} - {e}")
                continue
        
        # 如果所有选择器都失败，保存页面 HTML 用于调试
        await self.debug_page_structure(f"inline_{inline_prefix}_failed.html")
        await self.take_screenshot(f"inline_{inline_prefix}_failed")
        raise Exception(f"无法找到内联添加按钮: {inline_prefix} (实际: {actual_prefix})")
    
    async def take_screenshot(self, name: str):
        """截图（改进版 - 避免超时）"""
        import os
        screenshot_dir = "backend/tests/admin/screenshots"
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)
        
        try:
            await self.page.screenshot(
                path=f"{screenshot_dir}/{name}.png",
                timeout=10000  # 10秒超时
            )
            print(f"    ✓ 截图已保存: {name}.png")
        except Exception as e:
            print(f"    ⚠️  截图失败: {e}")
            # 尝试不等待字体加载
            try:
                await self.page.screenshot(
                    path=f"{screenshot_dir}/{name}.png",
                    timeout=5000
                )
                print(f"    ✓ 截图已保存（第二次尝试）: {name}.png")
            except:
                print(f"    ✗ 截图完全失败")
    
    async def debug_page_structure(self, filename: str = "page_structure.html"):
        """保存页面 HTML 结构用于调试"""
        import os
        debug_dir = "backend/tests/admin/debug"
        if not os.path.exists(debug_dir):
            os.makedirs(debug_dir)
        try:
            content = await self.page.content()
            with open(f"{debug_dir}/{filename}", "w", encoding="utf-8") as f:
                f.write(content)
            print(f"    ✓ 调试 HTML 已保存: {filename}")
        except Exception as e:
            print(f"    ⚠️  保存调试 HTML 失败: {e}")
    
    async def wait_for_inline_to_load(self, inline_prefix: str, timeout: int = 5000):
        """等待内联表单加载完成"""
        try:
            # 等待内联组出现
            await self.page.wait_for_selector(
                f'[id*="{inline_prefix}"]',
                timeout=timeout
            )
            # 额外等待一点时间确保 JavaScript 初始化完成
            await self.page.wait_for_timeout(500)
        except Exception as e:
            print(f"    ⚠️  等待内联加载超时: {inline_prefix}")
    
    async def wait_for_js_initialization(self, field_pattern: str, timeout: int = 8000):
        """等待 JavaScript 初始化完成，将 __prefix__ 替换为实际索引"""
        try:
            # 等待可见的字段出现（不包含__prefix__）
            await self.page.wait_for_selector(
                f'[name*="{field_pattern}"][name*="-0-"]:not([name*="__prefix__"]):visible',
                timeout=timeout,
                state='visible'
            )
            print(f"    ✓ JavaScript 初始化完成: {field_pattern}")
        except Exception as e:
            # 超时不是致命错误，继续尝试
            print(f"    ⚠️  JavaScript 初始化超时: {field_pattern}，继续尝试")
            # 额外等待一点时间
            await self.page.wait_for_timeout(2000)
    
    def get_inline_field_name(self, inline_prefix: str, row_index: int, field_name: str) -> str:
        """
        获取内联字段的实际名称
        
        django-nested-admin 使用简化的命名：parties-0-client
        标准 Django Admin 使用：caseparty_set-0-client
        """
        # 映射表
        prefix_mapping = {
            'caseparty_set': 'parties',
            'caseassignment_set': 'assignments',
            'supervisingauthority_set': 'supervising_authorities',
            'casenumber_set': 'case_numbers',
            'caselog_set': 'logs',
            'caselogattachment_set': 'attachments',
            'accountcredential_set': 'accountcredential_set',  # 律师凭证使用标准命名
            'clientidentitydoc_set': 'identity_docs',
            'cases': 'cases',
        }
        
        actual_prefix = prefix_mapping.get(inline_prefix, inline_prefix)
        return f"{actual_prefix}-{row_index}-{field_name}"
    
    async def fill_raw_id_field(self, field_name: str, value: str):
        """填写 raw_id_fields（外键输入框）"""
        # raw_id_fields 使用 input 而不是 select
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
            except:
                continue
        
        raise Exception(f"无法找到 raw_id 字段: {field_name}")
    
    async def select_radio_button(self, field_name: str, value: str):
        """选择 radio button"""
        selector = f'input[name="{field_name}"][value="{value}"]'
        
        try:
            # 等待元素出现
            await self.page.wait_for_selector(selector, timeout=5000)
            element = await self.page.query_selector(selector)
            if element:
                await element.check(timeout=5000)
                print(f"    ✓ 选择 radio: {field_name} = {value}")
                return
        except:
            pass
        
        raise Exception(f"无法找到 radio button: {field_name}={value}")
    
    async def fill_field_smart(self, field_name: str, value: str):
        """智能填写字段（自动检测类型并选择最佳方法）"""
        print(f"  → 智能填写字段: {field_name} = {value}")
        
        # 尝试不同的方法，按优先级排序
        methods = [
            ('select', self.select_option),
            ('input', self.fill_field),
            ('raw_id', self.fill_raw_id_field),
            ('radio', self.select_radio_button),
        ]
        
        for method_name, method in methods:
            try:
                await method(field_name, value)
                return
            except Exception as e:
                print(f"    ⚠️  {method_name} 方法失败")
                continue
        
        # 所有方法都失败
        await self.debug_page_structure(f"smart_fill_{field_name}_failed.html")
        raise Exception(f"无法填写字段 {field_name}，所有方法都失败")
    
    async def measure_page_load_time(self, url: str) -> float:
        """测量页面加载时间"""
        import time
        start = time.time()
        await self.page.goto(url)
        await self.page.wait_for_load_state('networkidle')
        end = time.time()
        return end - start
    
    async def search(self, query: str):
        """使用搜索功能"""
        print(f"  → 搜索: {query}")
        await self.page.fill('input[name="q"]', query)
        await self.page.click('input[type="submit"][value="Search"]')
        await self.page.wait_for_load_state('networkidle')
    
    async def apply_filter(self, filter_name: str, filter_value: str):
        """应用过滤器"""
        print(f"  → 应用过滤器: {filter_name}={filter_value}")
        await self.page.click(f'#changelist-filter a[href*="{filter_name}={filter_value}"]')
        await self.page.wait_for_load_state('networkidle')
    
    async def select_action(self, action_name: str):
        """选择 Admin Action"""
        print(f"  → 选择 Action: {action_name}")
        await self.page.select_option('select[name="action"]', action_name)
    
    async def select_all_rows(self):
        """选择所有行"""
        print(f"  → 选择所有行")
        await self.page.click('#action-toggle')
    
    async def execute_action(self):
        """执行 Action"""
        print(f"  → 执行 Action")
        await self.page.click('button[name="index"]')
        await self.page.wait_for_load_state('networkidle')
    
    def assert_true(self, condition: bool, message: str = ""):
        """断言为真"""
        if not condition:
            raise AssertionError(message or "断言失败")
    
    def assert_false(self, condition: bool, message: str = ""):
        """断言为假"""
        if condition:
            raise AssertionError(message or "断言失败")
    
    def assert_equals(self, actual: Any, expected: Any, message: str = ""):
        """断言相等"""
        if actual != expected:
            raise AssertionError(
                message or f"期望 {expected}，实际 {actual}"
            )
    
    def assert_contains(self, text: str, substring: str, message: str = ""):
        """断言包含"""
        if substring not in text:
            raise AssertionError(
                message or f"'{text}' 不包含 '{substring}'"
            )
    
    # ========== 验证错误检测方法（阶段4新增） ==========
    
    async def check_validation_error(
        self,
        field_name: Optional[str] = None,
        expected_message: Optional[str] = None
    ) -> bool:
        """
        检查验证错误
        
        Args:
            field_name: 字段名（可选），如果指定则只检查该字段的错误
            expected_message: 期望的错误消息（可选），如果指定则检查消息内容
            
        Returns:
            是否检测到验证错误
        """
        print(f"  → 检查验证错误" + (f" (字段: {field_name})" if field_name else ""))
        
        # 错误消息选择器（按优先级）
        error_selectors = [
            '.errorlist li',                    # Django 标准错误
            '.errors',                          # 通用错误
            '.field-error',                     # 字段错误
            '.inline-errors',                   # 内联错误
            '[class*="error"]',                 # 包含 error 的类
            '.djn-error',                       # django-nested-admin 错误
            '.errornote',                       # 错误提示
        ]
        
        # 如果指定了字段名，尝试查找该字段的错误
        if field_name:
            # 尝试查找字段相关的错误
            field_error_selectors = [
                f'#{field_name} + .errorlist',
                f'[name="{field_name}"] + .errorlist',
                f'.field-{field_name} .errorlist',
                f'[id*="{field_name}"] .errorlist',
            ]
            error_selectors = field_error_selectors + error_selectors
        
        # 尝试所有选择器
        for selector in error_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                if elements:
                    # 检查是否有可见的错误元素
                    for element in elements:
                        is_visible = await element.is_visible()
                        if is_visible:
                            error_text = await element.inner_text()
                            error_text = error_text.strip()
                            
                            if error_text:
                                # 如果指定了期望的消息，检查是否匹配
                                if expected_message:
                                    if expected_message in error_text:
                                        print(f"    ✓ 检测到验证错误: {error_text}")
                                        return True
                                else:
                                    print(f"    ✓ 检测到验证错误: {error_text}")
                                    return True
            except Exception as e:
                continue
        
        print(f"    ℹ️  未检测到验证错误")
        return False
    
    async def get_validation_errors(self) -> list[Dict[str, str]]:
        """
        获取所有验证错误
        
        Returns:
            错误列表，每个错误包含 'field', 'message', 'location'
        """
        print(f"  → 获取所有验证错误")
        
        errors = []
        
        # 错误消息选择器
        error_selectors = [
            ('.errorlist li', 'main_form'),           # Django 标准错误
            ('.errors', 'main_form'),                 # 通用错误
            ('.field-error', 'main_form'),            # 字段错误
            ('.inline-errors', 'inline'),             # 内联错误
            ('.djn-error', 'inline'),                 # django-nested-admin 错误
            ('.errornote', 'main_form'),              # 错误提示
        ]
        
        for selector, location in error_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                for element in elements:
                    is_visible = await element.is_visible()
                    if is_visible:
                        error_text = await element.inner_text()
                        error_text = error_text.strip()
                        
                        if error_text:
                            # 尝试找到关联的字段
                            field_name = await self._find_error_field(element)
                            
                            errors.append({
                                'field': field_name or 'unknown',
                                'message': error_text,
                                'location': location
                            })
            except Exception as e:
                continue
        
        if errors:
            print(f"    ✓ 找到 {len(errors)} 个验证错误")
            for error in errors:
                print(f"      - {error['field']}: {error['message']}")
        else:
            print(f"    ℹ️  未找到验证错误")
        
        return errors
    
    async def verify_no_validation_errors(self) -> bool:
        """
        验证没有验证错误
        
        Returns:
            是否没有错误（True = 没有错误，False = 有错误）
        """
        print(f"  → 验证没有验证错误")
        
        errors = await self.get_validation_errors()
        
        if not errors:
            print(f"    ✓ 确认没有验证错误")
            return True
        else:
            print(f"    ✗ 发现 {len(errors)} 个验证错误")
            return False
    
    async def _find_error_field(self, error_element) -> Optional[str]:
        """
        尝试找到错误消息关联的字段名
        
        Args:
            error_element: 错误元素
            
        Returns:
            字段名（如果找到）
        """
        try:
            # 尝试向上查找父元素，找到包含字段的容器
            parent = await error_element.evaluate_handle('el => el.parentElement')
            
            # 尝试查找相邻的 input/select/textarea
            field = await parent.query_selector('input, select, textarea')
            if field:
                field_name = await field.get_attribute('name')
                if field_name:
                    return field_name
            
            # 尝试查找父元素的 class 或 id
            parent_class = await parent.get_attribute('class')
            if parent_class and 'field-' in parent_class:
                # 提取字段名，如 'field-name' -> 'name'
                for cls in parent_class.split():
                    if cls.startswith('field-'):
                        return cls.replace('field-', '')
            
            parent_id = await parent.get_attribute('id')
            if parent_id:
                return parent_id
        except:
            pass
        
        return None
    
    async def wait_for_validation_error(
        self,
        timeout: int = 5000,
        field_name: Optional[str] = None
    ) -> bool:
        """
        等待验证错误消息出现（支持动态加载）
        
        Args:
            timeout: 超时时间（毫秒）
            field_name: 字段名（可选），如果指定则只等待该字段的错误
            
        Returns:
            是否检测到验证错误
        """
        print(f"  → 等待验证错误出现" + (f" (字段: {field_name})" if field_name else ""))
        
        # 错误消息选择器
        error_selectors = [
            '.errorlist li',
            '.errors',
            '.field-error',
            '.inline-errors',
            '[class*="error"]',
            '.djn-error',
            '.errornote',
        ]
        
        # 如果指定了字段名，添加字段特定的选择器
        if field_name:
            field_error_selectors = [
                f'#{field_name} + .errorlist',
                f'[name="{field_name}"] + .errorlist',
                f'.field-{field_name} .errorlist',
                f'[id*="{field_name}"] .errorlist',
            ]
            error_selectors = field_error_selectors + error_selectors
        
        # 尝试等待任何一个错误选择器出现
        for selector in error_selectors:
            try:
                await self.page.wait_for_selector(
                    selector,
                    timeout=timeout,
                    state='visible'
                )
                print(f"    ✓ 检测到验证错误 (选择器: {selector})")
                return True
            except Exception as e:
                continue
        
        print(f"    ℹ️  超时未检测到验证错误")
        return False
    
    async def fix_validation_error(
        self,
        field_name: str,
        correct_value: str,
        is_inline: bool = False,
        inline_prefix: Optional[str] = None,
        row_index: Optional[int] = None
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
        print(f"  → 修正验证错误: {field_name} = {correct_value}")
        
        # 如果是内联字段，构造完整的字段名
        if is_inline and inline_prefix is not None and row_index is not None:
            full_field_name = self.get_inline_field_name(inline_prefix, row_index, field_name)
        else:
            full_field_name = field_name
        
        # 尝试填写字段
        try:
            # 先尝试使用智能填写
            await self.fill_field_smart(full_field_name, correct_value)
            print(f"    ✓ 字段已修正")
        except Exception as e:
            print(f"    ⚠️  修正失败: {e}")
            # 尝试直接填写
            try:
                await self.fill_field(full_field_name, correct_value)
                print(f"    ✓ 字段已修正（使用 fill_field）")
            except Exception as e2:
                print(f"    ✗ 修正失败: {e2}")
                raise
