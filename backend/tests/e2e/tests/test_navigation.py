"""
Django Admin E2E 测试 — 导航结构

验证 Hub 页面、侧边栏、导航链接等 UI 导航功能。

运行方式：
    cd backend
    pytest tests/e2e/tests/test_navigation.py -v
    pytest tests/e2e/tests/test_navigation.py -v --headed
"""

import pytest
from playwright.sync_api import Page, ViewportSize, expect

# ------------------------------------------------------------------
# 1. 办案 Hub 页面加载
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_case_handling_hub_loads(admin_page: Page, base_url: str) -> None:
    """访问 /admin/case-handling/，验证 Hub 页面渲染，包含办案卡片。"""
    admin_page.goto(f"{base_url}/admin/case-handling/")
    admin_page.wait_for_load_state("domcontentloaded")
    # 页面主体应包含 case-handling-page 容器
    expect(admin_page.locator(".case-handling-page")).to_be_visible()
    # 应有至少一张 tool-card（当事人 / 合同 / 案件）
    cards = admin_page.locator(".tool-card")
    expect(cards.first).to_be_visible()
    assert cards.count() >= 1, "Hub page should contain at least one tool card"


# ------------------------------------------------------------------
# 2. 其他工具 Hub 页面加载
# ------------------------------------------------------------------

def test_other_tools_hub_loads(admin_page: Page, base_url: str) -> None:
    """访问 /admin/automation/other-tools/，验证工具聚合页渲染。"""
    admin_page.goto(f"{base_url}/admin/automation/other-tools/")
    admin_page.wait_for_load_state("domcontentloaded")
    # 页面主体应包含 other-tools-page 容器
    expect(admin_page.locator(".other-tools-page")).to_be_visible()
    # 应有工具卡片
    cards = admin_page.locator(".tool-card")
    expect(cards.first).to_be_visible()


# ------------------------------------------------------------------
# 3. 侧边栏包含预期分区
# ------------------------------------------------------------------

def test_sidebar_has_expected_sections(admin_page: Page, base_url: str) -> None:
    """验证侧边栏包含虚拟菜单（办案、其他工具）。

    注：reminders app 在 admin_customization._HIDDEN_APP_LABELS 中被有意隐藏
    （日历即首页，无需在侧边栏重复入口），故不应断言「提醒」出现在侧边栏。
    """
    # 访问任意 admin 页面以触发侧边栏渲染
    admin_page.goto(f"{base_url}/admin/")
    admin_page.wait_for_load_state("domcontentloaded")
    sidebar = admin_page.locator("#nav-sidebar")
    # 侧边栏应在 DOM 中（可能隐藏在窄屏，但 DOM 应存在）
    expect(sidebar).to_be_attached()
    sidebar_text = sidebar.inner_text()
    # 虚拟「办案」菜单应出现
    assert "办案" in sidebar_text, (
        f"Sidebar should contain '办案', got: {sidebar_text[:200]}"
    )
    # 虚拟「其他工具」菜单应出现
    assert "其他工具" in sidebar_text, (
        f"Sidebar should contain '其他工具', got: {sidebar_text[:200]}"
    )


# ------------------------------------------------------------------
# 4. Hub 页面卡片链接可导航
# ------------------------------------------------------------------

def test_case_handling_hub_links_work(
    admin_page: Page, base_url: str
) -> None:
    """在办案 Hub 页面点击一个子链接（如 客户/当事人），验证跳转正确。"""
    admin_page.goto(f"{base_url}/admin/case-handling/")
    admin_page.wait_for_load_state("domcontentloaded")
    # 找到包含「当事人」的子链接
    link = admin_page.locator("a.child-link, a.tool-name").filter(
        has_text="当事人"
    ).first
    expect(link).to_be_visible()
    link.click()
    admin_page.wait_for_load_state("domcontentloaded")
    # 跳转后 URL 应包含 client（当事人管理的 app_label）
    url = admin_page.url
    assert "client" in url.lower(), (
        f"Expected URL to contain 'client' after clicking '当事人' link, got: {url}"
    )


# ------------------------------------------------------------------
# 5. 日历页为默认着陆页
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_calendar_is_default_landing(
    admin_page: Page, base_url: str
) -> None:
    """登录后直接访问 /admin/，验证最终 URL 包含 reminder 或 calendar。"""
    admin_page.goto(f"{base_url}/admin/")
    admin_page.wait_for_load_state("domcontentloaded")
    url = admin_page.url
    assert "reminder" in url.lower() or "calendar" in url.lower(), (
        f"Expected landing URL to contain 'reminder' or 'calendar', got: {url}"
    )


# ------------------------------------------------------------------
# 6. 移动端抽屉侧边栏
# ------------------------------------------------------------------

MOBILE_VIEWPORT: ViewportSize = {"width": 375, "height": 667}
DRAWER_TRANSITION_WAIT_MS = 350  # 抽屉 transform 过渡时长 0.22s + 余量


def _open_mobile_drawer(admin_page: Page, base_url: str) -> None:
    """在移动端视口下打开登录页并展开抽屉侧边栏（供多个用例复用）。"""
    admin_page.set_viewport_size(MOBILE_VIEWPORT)
    admin_page.goto(f"{base_url}/admin/")
    admin_page.wait_for_load_state("domcontentloaded")
    toggle = admin_page.locator("#fc-mobile-nav-toggle")
    expect(toggle).to_be_visible()
    toggle.click()
    body_classes = admin_page.locator("body").get_attribute("class") or ""
    assert "fc-mobile-nav-open" in body_classes, (
        "Body should have 'fc-mobile-nav-open' after clicking hamburger"
    )
    admin_page.wait_for_timeout(DRAWER_TRANSITION_WAIT_MS)


def test_mobile_hamburger_toggle_hidden_on_desktop(
    admin_page: Page, base_url: str
) -> None:
    """桌面端视口下汉堡按钮不可见，桌面侧边栏行为不受影响。"""
    admin_page.goto(f"{base_url}/admin/")
    admin_page.wait_for_load_state("domcontentloaded")
    toggle = admin_page.locator("#fc-mobile-nav-toggle")
    expect(toggle).to_be_hidden()
    body_classes = admin_page.locator("body").get_attribute("class") or ""
    assert "fc-mobile-nav-open" not in body_classes


def test_mobile_drawer_opens_and_shows_menus(
    admin_page: Page, base_url: str
) -> None:
    """移动端视口下：汉堡按钮可见，点击展开抽屉且包含核心菜单。"""
    _open_mobile_drawer(admin_page, base_url)
    sidebar = admin_page.locator("#nav-sidebar")
    # 抽屉应滑入可视区（初始 transform 为 -105%，展开后 x >= 0）
    box = sidebar.bounding_box()
    assert box is not None, "Sidebar should have a bounding box when open"
    assert box["x"] >= 0, (
        f"Sidebar drawer should be in viewport, got x={box['x']}"
    )
    # 遮罩应可见
    expect(admin_page.locator(".fc-mobile-nav-backdrop")).to_be_visible()
    # 抽屉内容包含虚拟菜单（办案 / 其他工具）
    sidebar_text = sidebar.inner_text()
    assert "办案" in sidebar_text, (
        f"Drawer should contain '办案', got: {sidebar_text[:200]}"
    )
    assert "其他工具" in sidebar_text, (
        f"Drawer should contain '其他工具', got: {sidebar_text[:200]}"
    )


def test_mobile_drawer_backdrop_click_closes(
    admin_page: Page, base_url: str
) -> None:
    """移动端视口下：点击遮罩关闭抽屉。"""
    _open_mobile_drawer(admin_page, base_url)
    # 遮罩覆盖整个视口，其几何中心落在 280px 宽的侧边栏内部，
    # 会被侧边栏内容拦截点击，故显式点击侧边栏右侧（x=340 > 280）的遮罩区域。
    admin_page.locator(".fc-mobile-nav-backdrop").click(
        position={"x": 340, "y": 300}
    )
    body_classes = admin_page.locator("body").get_attribute("class") or ""
    assert "fc-mobile-nav-open" not in body_classes, (
        "Drawer should close after clicking backdrop"
    )
    admin_page.wait_for_timeout(DRAWER_TRANSITION_WAIT_MS)
    box = admin_page.locator("#nav-sidebar").bounding_box()
    assert box is not None and box["x"] < 0, (
        f"Sidebar drawer should slide out of viewport, got x={box['x'] if box else None}"
    )


def test_mobile_drawer_link_navigates_to_case_handling(
    admin_page: Page, base_url: str
) -> None:
    """移动端视口下：通过抽屉点击「办案」可进入办案 Hub 页面。

    这是本次修复的核心场景：手机用户必须能从日历页切换到案件/合同。
    """
    _open_mobile_drawer(admin_page, base_url)
    link = admin_page.locator("#nav-sidebar a").filter(
        has_text="办案"
    ).first
    expect(link).to_be_visible()
    link.click()
    admin_page.wait_for_load_state("domcontentloaded")
    assert "case-handling" in admin_page.url, (
        f"Expected URL to contain 'case-handling' after clicking '办案', "
        f"got: {admin_page.url}"
    )
