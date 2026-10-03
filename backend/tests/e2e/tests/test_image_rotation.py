"""
图片旋转工具 — 详细 E2E 测试

验证 image_rotation.html 拆分后：
- 所有 JS / CSS 静态文件正确加载（无 404）
- Alpine.js 应用正常初始化
- Tab 导航功能正常
- 工具 Tab 和历史 Tab 的 UI 元素完整
- 弹窗（模态框）功能正常

运行方式：
    cd backend
    DATABASE_PATH=/tmp/e2e_test.sqlite3 DB_NAME=test_fachuan_dev DJANGO_ALLOW_ASYNC_UNSAFE=true \
        .venv/bin/pytest tests/e2e/tests/test_image_rotation.py -v
"""

import re

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def rotation_page(admin_page: Page, base_url: str) -> Page:
    """打开图片旋转工具页面并等待 Alpine.js 初始化完成。"""
    response = admin_page.goto(f"{base_url}/admin/image_rotation/imagerotationtool/")
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("networkidle")
    # 等待 Alpine.js 挂载 x-data
    admin_page.wait_for_selector("[x-data]", state="attached", timeout=10000)
    return admin_page


# ------------------------------------------------------------------
# 1. 静态资源加载
# ------------------------------------------------------------------


class TestStaticAssets:
    """验证所有 JS / CSS 文件正确加载，无 404。"""

    def test_no_console_errors_on_load(self, rotation_page: Page) -> None:
        """页面加载时不应有 404 或 JS 错误。"""
        errors = []
        rotation_page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

        # 重新加载以捕获完整控制台输出
        rotation_page.reload()
        rotation_page.wait_for_load_state("networkidle")
        rotation_page.wait_for_selector("[x-data]", state="attached", timeout=10000)

        # 过滤掉已知的非关键警告（如 favicon 404）
        critical_errors = [
            e for e in errors if "404" in e or "Failed to load" in e or "SyntaxError" in e or "ReferenceError" in e
        ]
        assert not critical_errors, f"页面加载有关键错误: {critical_errors}"

    def test_css_loaded(self, rotation_page: Page) -> None:
        """CSS 文件加载成功，关键样式生效。"""
        # 检查 rotation-container 的 max-width 生效（来自 image_rotation.css）
        container = rotation_page.locator(".rotation-container")
        max_width = container.evaluate("el => getComputedStyle(el).maxWidth")
        assert max_width == "1200px", f"CSS 未生效，max-width={max_width}"

    def test_utils_js_loaded(self, rotation_page: Page) -> None:
        """image_rotation_utils.js 加载成功。"""
        has_utils = rotation_page.evaluate("typeof window.ImageRotationUtils !== 'undefined'")
        assert has_utils, "ImageRotationUtils 未定义"

    def test_file_module_loaded(self, rotation_page: Page) -> None:
        """image_rotation_file.js 加载成功。"""
        has_file = rotation_page.evaluate("typeof window.ImageRotationFile !== 'undefined'")
        assert has_file, "ImageRotationFile 未定义"

    def test_export_module_loaded(self, rotation_page: Page) -> None:
        """image_rotation_export.js 加载成功。"""
        has_export = rotation_page.evaluate("typeof window.ImageRotationExport !== 'undefined'")
        assert has_export, "ImageRotationExport 未定义"

    def test_history_module_loaded(self, rotation_page: Page) -> None:
        """image_rotation_history.js 加载成功。"""
        has_history = rotation_page.evaluate("typeof window.ImageRotationHistory !== 'undefined'")
        assert has_history, "ImageRotationHistory 未定义"


# ------------------------------------------------------------------
# 2. Alpine.js 初始化
# ------------------------------------------------------------------


class TestAlpineInit:
    """验证 Alpine.js 应用正确初始化。"""

    def test_alpine_component_mounted(self, rotation_page: Page) -> None:
        """x-data 组件已挂载。"""
        component = rotation_page.locator("[x-data]")
        expect(component).to_be_attached()

    def test_initial_state_correct(self, rotation_page: Page) -> None:
        """初始状态：currentView='tool', images=[]。"""
        state = rotation_page.evaluate("""
            (() => {
                const el = document.querySelector('[x-data]');
                const data = Alpine.$data(el);
                return { currentView: data.currentView, imageCount: data.images.length };
            })()
        """)
        assert state["currentView"] == "tool"
        assert state["imageCount"] == 0

    def test_module_methods_attached(self, rotation_page: Page) -> None:
        """模块方法已挂载到 Alpine 组件上。"""
        methods = rotation_page.evaluate("""
            (() => {
                const el = document.querySelector('[x-data]');
                const data = Alpine.$data(el);
                return {
                    handleFileSelect: typeof data.handleFileSelect,
                    exportPdf: typeof data.exportPdf,
                    saveTaskToHistory: typeof data.saveTaskToHistory,
                    loadHistory: typeof data.loadHistory,
                    rotateLeft: typeof data.rotateLeft,
                    clearAll: typeof data.clearAll,
                    renderThumbnail: typeof data.renderThumbnail,
                };
            })()
        """)
        for name, typ in methods.items():
            assert typ == "function", f"方法 {name} 类型为 {typ}，应为 function"


# ------------------------------------------------------------------
# 3. Tab 导航
# ------------------------------------------------------------------


class TestTabNavigation:
    """验证 Tab 切换功能。"""

    def test_tab_buttons_visible(self, rotation_page: Page) -> None:
        """两个 Tab 按钮可见。"""
        tool_tab = rotation_page.locator(".tab-btn", has_text="旋转工具")
        history_tab = rotation_page.locator(".tab-btn", has_text="历史记录")
        expect(tool_tab).to_be_visible()
        expect(history_tab).to_be_visible()

    def test_tool_tab_active_by_default(self, rotation_page: Page) -> None:
        """默认选中旋转工具 Tab。"""
        tool_tab = rotation_page.locator(".tab-btn", has_text="旋转工具")
        expect(tool_tab).to_have_class(re.compile(r"active"))

    def test_switch_to_history_tab(self, rotation_page: Page) -> None:
        """切换到历史记录 Tab。"""
        rotation_page.locator(".tab-btn", has_text="历史记录").click()
        rotation_page.wait_for_timeout(500)

        # 验证历史 Tab 内容可见
        history_title = rotation_page.locator("h2.rotation-title", has_text="历史记录")
        expect(history_title).to_be_visible()

        # 验证工具 Tab 内容隐藏
        upload_box = rotation_page.locator(".upload-box")
        expect(upload_box).to_be_hidden()

    def test_switch_back_to_tool_tab(self, rotation_page: Page) -> None:
        """从历史切回工具 Tab。"""
        # 先切到历史
        rotation_page.locator(".tab-btn", has_text="历史记录").click()
        rotation_page.wait_for_timeout(500)

        # 再切回工具
        rotation_page.locator(".tab-btn", has_text="旋转工具").click()
        rotation_page.wait_for_timeout(500)

        upload_box = rotation_page.locator(".upload-box")
        expect(upload_box).to_be_visible()


# ------------------------------------------------------------------
# 4. 旋转工具 Tab
# ------------------------------------------------------------------


class TestToolTab:
    """验证旋转工具 Tab 的 UI 元素。"""

    def test_header_visible(self, rotation_page: Page) -> None:
        """标题和副标题可见。"""
        title = rotation_page.locator(".rotation-title", has_text="图片/PDF 自动旋转")
        expect(title).to_be_visible()

        subtitle = rotation_page.locator(".rotation-subtitle")
        expect(subtitle).to_be_visible()

    def test_back_link_visible(self, rotation_page: Page) -> None:
        """返回工具列表链接可见。"""
        back = rotation_page.locator(".back-link", has_text="返回工具列表")
        expect(back).to_be_visible()

    def test_upload_box_visible_when_empty(self, rotation_page: Page) -> None:
        """images 为空时，上传区域可见。"""
        upload_box = rotation_page.locator(".upload-box")
        expect(upload_box).to_be_visible()
        expect(upload_box).to_contain_text("点击或拖拽上传图片/PDF")

    def test_hint_box_visible(self, rotation_page: Page) -> None:
        """提示信息可见。"""
        hint = rotation_page.locator(".hint-box", has_text="支持 JPG")
        expect(hint).to_be_visible()

    def test_file_input_accepts_correct_types(self, rotation_page: Page) -> None:
        """文件输入框 accept 属性正确。"""
        file_input = rotation_page.locator("input[type='file']")
        accept = file_input.get_attribute("accept")
        assert "image/jpeg" in accept
        assert ".pdf" in accept

    def test_stats_bar_hidden_when_empty(self, rotation_page: Page) -> None:
        """images 为空时，统计栏隐藏。"""
        stats = rotation_page.locator(".stats-bar")
        expect(stats).to_be_hidden()

    def test_form_actions_hidden_when_empty(self, rotation_page: Page) -> None:
        """images 为空时，操作按钮隐藏。"""
        actions = rotation_page.locator(".form-actions")
        expect(actions).to_be_hidden()


# ------------------------------------------------------------------
# 5. 历史记录 Tab
# ------------------------------------------------------------------


class TestHistoryTab:
    """验证历史记录 Tab 的 UI 元素。"""

    @pytest.fixture(autouse=True)
    def switch_to_history(self, rotation_page: Page) -> None:
        """每个测试前切换到历史 Tab。"""
        rotation_page.locator(".tab-btn", has_text="历史记录").click()
        rotation_page.wait_for_timeout(500)
        self.page = rotation_page

    def test_history_title_visible(self) -> None:
        """历史记录标题可见。"""
        title = self.page.locator("h2.rotation-title", has_text="历史记录")
        expect(title).to_be_visible()

    def test_refresh_button_visible(self) -> None:
        """刷新按钮可见。"""
        btn = self.page.locator("button", has_text="刷新")
        expect(btn).to_be_visible()

    def test_history_list_or_empty_visible(self) -> None:
        """历史列表或空状态可见。"""
        # 可能有历史记录，也可能是空的
        empty_msg = self.page.locator(".history-empty", has_text="暂无历史记录")
        items = self.page.locator(".history-item")
        # 至少一个可见
        either_visible = empty_msg.is_visible() or items.count() > 0
        assert either_visible, "历史列表和空状态都不可见"


# ------------------------------------------------------------------
# 6. 弹窗 / 模态框
# ------------------------------------------------------------------


class TestModals:
    """验证弹窗功能。"""

    def test_delete_confirm_modal_hidden_by_default(self, rotation_page: Page) -> None:
        """删除确认弹窗默认隐藏。"""
        modal = rotation_page.locator(".modal-overlay", has_text="确认删除")
        expect(modal).to_be_hidden()

    def test_image_preview_modal_hidden_by_default(self, rotation_page: Page) -> None:
        """图片预览弹窗默认隐藏。"""
        modal = rotation_page.locator(".modal-overlay").first
        expect(modal).to_be_hidden()


# ------------------------------------------------------------------
# 7. API 端点可达性
# ------------------------------------------------------------------


class TestAPIEndpoints:
    """验证关键 API 端点可访问（需登录态）。"""

    def test_jobs_list_api(self, rotation_page: Page, base_url: str) -> None:
        """历史任务列表 API 可访问（标准分页信封）。"""
        response = rotation_page.evaluate("""
            fetch('/api/v1/image-rotation/jobs?page=1&page_size=5')
                .then(r => r.json())
                .then(d => ({ hasItems: Array.isArray(d.items), total: d.total, totalPages: d.total_pages }))
        """)
        assert response["hasItems"] is True
        assert isinstance(response["total"], int)
        assert isinstance(response["totalPages"], int)
