"""
Django Admin E2E 测试 — 案件管理 (Case)

覆盖 Case 模型的增删改查、详情页、材料页、诉讼费计算器等 Admin 页面。
"""

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
def test_case_search(
    admin_page: Page, base_url: str, e2e_case
) -> None:
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
    change_form = admin_page.locator("#change-form")
    expect(change_form).to_be_visible()
    # 验证核心字段存在
    name_input = admin_page.locator("input#id_name")
    expect(name_input).to_be_visible()
    # contract 使用 Django admin autocomplete 验证 widget 存在
    contract_widget = admin_page.locator("#select2-id_contract-container")
    expect(contract_widget).to_be_visible()


@pytest.mark.crud
def test_case_create(
    admin_page: Page, base_url: str, e2e_contract
) -> None:
    """创建一个案件并提交。"""
    admin_page.goto(f"{base_url}/admin/cases/case/add/")
    admin_page.wait_for_load_state("domcontentloaded")

    # 填写案件名称
    admin_page.fill("input#id_name", "E2E新案件")

    # contract 是 Django admin autocomplete 字段
    # 需要先输入文本触发搜索，再从下拉列表中选择匹配项
    contract_widget = admin_page.locator("#select2-id_contract-container")
    contract_widget.click()
    # 在弹出的搜索框中输入合同名称前几个字符
    search_input = admin_page.locator(".select2-search__field").last
    search_input.fill(e2e_contract.name[:8])
    admin_page.wait_for_timeout(500)
    # 选择下拉结果中的第一个匹配项
    admin_page.locator(".select2-results__option--highlighted").first.click()

    # 提交
    admin_page.click("input[name='_save']")
    admin_page.wait_for_load_state("domcontentloaded")

    # 成功保存后应跳转回 changelist
    expect(admin_page).to_have_url(f"{base_url}/admin/cases/case/")
    success_msg = admin_page.locator(".messagelist .success")
    expect(success_msg).to_be_visible()


# ------------------------------------------------------------------
# 编辑页
# ------------------------------------------------------------------


@pytest.mark.crud
def test_case_change_page(
    admin_page: Page, base_url: str, e2e_case
) -> None:
    """访问已有案件的编辑页，验证名称字段正确回显。"""
    url = f"{base_url}/admin/cases/case/{e2e_case.pk}/change/"
    admin_page.goto(url)
    admin_page.wait_for_load_state("domcontentloaded")

    change_form = admin_page.locator("#change-form")
    expect(change_form).to_be_visible()
    name_input = admin_page.locator("input#id_name")
    expect(name_input).to_have_value(e2e_case.name)


# ------------------------------------------------------------------
# 详情页
# ------------------------------------------------------------------


@pytest.mark.crud
def test_case_detail_page(
    admin_page: Page, base_url: str, e2e_case
) -> None:
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
def test_case_materials_page(
    admin_page: Page, base_url: str, e2e_case
) -> None:
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
