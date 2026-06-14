"""
Django Admin E2E 测试 — 工具和杂项页面

验证各类工具页面（批量打印、PDF拆分、文档转换、快递查询、法律研究等）
以及工作流、聊天记录、工作台、消息中心等管理页面正常加载。

运行方式：
    cd backend
    pytest tests/e2e/tests/test_tools.py -v
    pytest tests/e2e/tests/test_tools.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect


# ------------------------------------------------------------------
# 聊天记录
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_chatrecord_project_list(admin_page: Page, base_url: str) -> None:
    """访问聊天记录项目列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/chat_records/chatrecordproject/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 工作流
# ------------------------------------------------------------------

@pytest.mark.smoke
def test_workflow_template_list(admin_page: Page, base_url: str) -> None:
    """访问工作流模板列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/workflow/workflowtemplate/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


@pytest.mark.smoke
def test_workflow_run_list(admin_page: Page, base_url: str) -> None:
    """访问工作流运行列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/workflow/workflowrun/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 工作台
# ------------------------------------------------------------------

def test_workbench_session_list(admin_page: Page, base_url: str) -> None:
    """访问工作台会话列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/workbench/workbenchsession/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 消息中心
# ------------------------------------------------------------------

def test_message_source_list(admin_page: Page, base_url: str) -> None:
    """访问消息来源列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/message_hub/messagesource/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


def test_inbox_message_list(admin_page: Page, base_url: str) -> None:
    """访问收件箱消息列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/message_hub/inboxmessage/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 批量打印
# ------------------------------------------------------------------

def test_batch_printing_tool(admin_page: Page, base_url: str) -> None:
    """访问批量打印工具页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/batch_printing/batchprintingtool/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# PDF 拆分
# ------------------------------------------------------------------

def test_pdf_splitting_tool(admin_page: Page, base_url: str) -> None:
    """访问 PDF 拆分工具页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/pdf_splitting/pdfsplittingtool/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 文档转换
# ------------------------------------------------------------------

def test_doc_convert_tool(admin_page: Page, base_url: str) -> None:
    """访问文档转换工具页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/doc_convert/docconverttool/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 快递查询
# ------------------------------------------------------------------

def test_express_query_tool(admin_page: Page, base_url: str) -> None:
    """访问快递查询工具页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/express_query/expressquerytool/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 法律研究
# ------------------------------------------------------------------

def test_legal_research_task_list(admin_page: Page, base_url: str) -> None:
    """访问法律研究任务列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/legal_research/legalresearchtask/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 法律解决方案
# ------------------------------------------------------------------

def test_legal_solution_task_list(admin_page: Page, base_url: str) -> None:
    """访问法律解决方案任务列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/legal_solution/solutiontask/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 图片旋转
# ------------------------------------------------------------------

def test_image_rotation_tool(admin_page: Page, base_url: str) -> None:
    """访问图片旋转工具页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/image_rotation/imagerotationtool/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 发票识别
# ------------------------------------------------------------------

def test_invoice_recognition_task_list(
    admin_page: Page, base_url: str
) -> None:
    """访问发票识别任务列表页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/invoice_recognition/invoicerecognitiontask/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 文档解析
# ------------------------------------------------------------------

def test_document_parsing_tool(admin_page: Page, base_url: str) -> None:
    """访问文档解析工具页，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/document_parsing/documentparsingtool/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")


# ------------------------------------------------------------------
# 证据排序
# ------------------------------------------------------------------

def test_evidence_sorting(admin_page: Page, base_url: str) -> None:
    """访问证据排序页面，验证页面正常加载。"""
    response = admin_page.goto(
        f"{base_url}/admin/evidence_sorting/evidencesorting/"
    )
    assert response is not None
    assert response.status < 500
    admin_page.wait_for_load_state("domcontentloaded")
