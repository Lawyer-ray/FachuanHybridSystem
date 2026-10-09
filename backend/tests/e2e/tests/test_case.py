"""
Django Admin E2E 测试 — 案件管理 (Case)

覆盖 Case 模型的增删改查、详情页、材料页、诉讼费计算器等 Admin 页面。
"""

import re

import pytest
from playwright.sync_api import Page, expect

# ------------------------------------------------------------------
# 列表页
# ------------------------------------------------------------------


@pytest.mark.crud
def test_case_list_page(admin_page: Page, base_url: str) -> None:
    """访问案件列表页，验证页面正常加载。"""
    admin_page.goto(f"{base_url}/admin/cases/case/")
    admin_page.wait_for_load_state("domcontentloaded")
    changelist = admin_page.locator("#changelist")
    expect(changelist).to_be_visible()


@pytest.mark.crud
def test_case_search(admin_page: Page, base_url: str, e2e_case) -> None:
    """在列表页使用搜索框搜索案件名称。"""
    admin_page.goto(f"{base_url}/admin/cases/case/")
    admin_page.wait_for_load_state("domcontentloaded")
    searchbar = admin_page.locator("#searchbar")
    expect(searchbar).to_be_visible()
    searchbar.fill(e2e_case.name)
    admin_page.locator("#changelist-search input[type='submit']").click()
    admin_page.wait_for_load_state("domcontentloaded")
    result_list = admin_page.locator("#result_list")
    expect(result_list).to_be_visible()
    expect(result_list).to_contain_text(e2e_case.name)


# ------------------------------------------------------------------
# 新增页
# ------------------------------------------------------------------


@pytest.mark.crud
def test_case_add_page(admin_page: Page, base_url: str) -> None:
    """访问案件新增页，验证表单正常加载。"""
    admin_page.goto(f"{base_url}/admin/cases/case/add/")
    admin_page.wait_for_load_state("domcontentloaded")
    # Django 6 的 admin 不再渲染 <form id="change-form">（只剩 body class），
    # 断言表单本体 + 保存按钮，语义等价
    expect(admin_page.locator("form").first).to_be_visible()
    expect(admin_page.locator("input[name='_save'], button[name='_save']").first).to_be_visible()
    # 验证核心字段存在
    name_input = admin_page.locator("input#id_name")
    expect(name_input).to_be_visible()
    # contract 是 autocomplete_fields：select2 把 <select id="id_contract"> 变成
    # hidden，另渲染 span.select2-container。可点的目标是 .select2-selection
    # （#select2-id_contract-container 是 placeholder 槽，空值时 height=0 不可见）
    contract_widget = admin_page.locator(
        "#select2-id_contract-container ~ .select2-selection__arrow, .field-contract .select2-selection"
    ).first
    expect(contract_widget).to_be_visible()


@pytest.mark.crud
def test_case_create(admin_page: Page, base_url: str, e2e_contract) -> None:
    """创建一个案件并提交。"""
    admin_page.goto(f"{base_url}/admin/cases/case/add/")
    admin_page.wait_for_load_state("domcontentloaded")

    # 填写案件名称
    admin_page.fill("input#id_name", "E2E新案件")

    # contract 走 select2（admin autocomplete）：点开 → 输入关键词 → 选第一项。
    # 搜索框由 select2 动态插入，需等它出现再 fill
    admin_page.locator(".field-contract .select2-selection").first.click()
    search_input = admin_page.locator(".select2-search__field, input.select2-search__field").first
    expect(search_input).to_be_visible(timeout=10000)
    search_input.fill(e2e_contract.name[:8])
    result = admin_page.locator(".select2-results__option").first
    expect(result).to_be_visible(timeout=10000)
    result.click()

    # 提交
    admin_page.click("input[name='_save']")
    admin_page.wait_for_load_state("domcontentloaded")

    # 成功保存后应跳转回 changelist（保存后带默认筛选 status__exact=active）
    expect(admin_page).to_have_url(re.compile(r"/admin/cases/case/\?"))
    success_msg = admin_page.locator(".messagelist .success")
    expect(success_msg).to_be_visible()


# ------------------------------------------------------------------
# 编辑页
# ------------------------------------------------------------------


@pytest.mark.crud
def test_case_change_page(admin_page: Page, base_url: str, e2e_case) -> None:
    """访问已有案件的编辑页，验证名称字段正确回显。"""
    url = f"{base_url}/admin/cases/case/{e2e_case.pk}/change/"
    admin_page.goto(url)
    admin_page.wait_for_load_state("domcontentloaded")

    # Django 6 的 admin 不再渲染 <form id="change-form">（只剩 body class），
    # 断言表单本体 + 保存按钮，语义等价
    expect(admin_page.locator("form").first).to_be_visible()
    expect(admin_page.locator("input[name='_save'], button[name='_save']").first).to_be_visible()
    name_input = admin_page.locator("input#id_name")
    expect(name_input).to_have_value(e2e_case.name)


# ------------------------------------------------------------------
# 详情页
# ------------------------------------------------------------------


@pytest.mark.crud
def test_case_detail_page(admin_page: Page, base_url: str, e2e_case) -> None:
    """访问案件详情页，验证页面正常加载。"""
    url = f"{base_url}/admin/cases/case/{e2e_case.pk}/detail/"
    admin_page.goto(url)
    admin_page.wait_for_load_state("domcontentloaded")

    body = admin_page.locator("body")
    expect(body).to_be_visible()
    # 详情页应包含案件名称
    expect(body).to_contain_text(e2e_case.name)
    # 页面不应出现 Django 错误页
    error_note = admin_page.locator("#traceback")
    expect(error_note).not_to_be_visible()


# ------------------------------------------------------------------
# 材料页
# ------------------------------------------------------------------


@pytest.mark.crud
def test_case_materials_page(admin_page: Page, base_url: str, e2e_case) -> None:
    """访问案件材料页，验证页面正常加载。"""
    url = f"{base_url}/admin/cases/case/{e2e_case.pk}/materials/"
    admin_page.goto(url)
    admin_page.wait_for_load_state("domcontentloaded")

    body = admin_page.locator("body")
    expect(body).to_be_visible()
    # 页面不应出现 Django 错误页
    error_note = admin_page.locator("#traceback")
    expect(error_note).not_to_be_visible()


# ------------------------------------------------------------------
# 诉讼费计算器
# ------------------------------------------------------------------


@pytest.mark.crud
def test_litigation_fee_calculator(admin_page: Page, base_url: str) -> None:
    """访问诉讼费计算器页面，验证页面正常加载。"""
    admin_page.goto(f"{base_url}/admin/cases/case/litigation-fee-calculator/")
    admin_page.wait_for_load_state("domcontentloaded")

    body = admin_page.locator("body")
    expect(body).to_be_visible()
    # 页面不应出现 Django 错误页
    error_note = admin_page.locator("#traceback")
    expect(error_note).not_to_be_visible()


# ------------------------------------------------------------------
# 编辑提交 + 删除（补缺：现有用例只到「编辑页回显」，无提交生效与删除全流程）
# ------------------------------------------------------------------


@pytest.mark.crud
def test_case_edit_submit_and_delete(admin_page: Page, base_url: str, e2e_case) -> None:
    """编辑已有案件名称并保存生效，随后走 admin 删除确认页完成删除。"""
    renamed = "E2E改名后案件"
    # --- 编辑提交：改名后列表可见新名字 ---
    admin_page.goto(f"{base_url}/admin/cases/case/{e2e_case.id}/change/")
    admin_page.wait_for_load_state("domcontentloaded")
    name_input = admin_page.locator("input#id_name")
    expect(name_input).to_have_value(e2e_case.name)
    name_input.fill(renamed)
    admin_page.click("input[name='_save']")
    admin_page.wait_for_load_state("domcontentloaded")
    # CaseAdmin 保存后跳自定义 detail 页（非默认 changelist），按前缀断言
    expect(admin_page).to_have_url(re.compile(r"/admin/cases/case/"))
    expect(admin_page.locator(".messagelist .success")).to_be_visible()

    admin_page.goto(f"{base_url}/admin/cases/case/")
    searchbar = admin_page.locator("#searchbar")
    searchbar.fill(renamed)
    admin_page.locator("#changelist-search input[type='submit']").click()
    admin_page.wait_for_load_state("domcontentloaded")
    result_list = admin_page.locator("#result_list")
    expect(result_list).to_contain_text(renamed)

    # --- 删除：change 页 deletelink → 确认页 → 确认提交 ---
    admin_page.goto(f"{base_url}/admin/cases/case/{e2e_case.id}/delete/")
    admin_page.wait_for_load_state("domcontentloaded")
    # 确认页应展示对象摘要，且表单为 POST 确认框
    expect(admin_page.locator("#content form")).to_be_visible()
    expect(admin_page.locator("body")).to_contain_text(renamed)
    admin_page.locator("#content form input[type='submit']").first.click()
    admin_page.wait_for_load_state("domcontentloaded")
    # 删除后回 changelist（可能带筛选参数），按前缀断言
    expect(admin_page).to_have_url(re.compile(r"/admin/cases/case/"))
    expect(admin_page.locator(".messagelist .success")).to_be_visible()

    # ORM 复核：确实删掉（而非仅 UI 提示）
    from apps.cases.models import Case

    assert not Case.objects.filter(pk=e2e_case.id).exists()
