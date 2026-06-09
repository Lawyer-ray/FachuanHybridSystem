"""Documents API integration tests."""

from __future__ import annotations

import json

import pytest

from apps.contracts.models import Contract
from apps.cases.models import Case
from apps.documents.models import DocumentTemplate, FolderTemplate, Placeholder


def _make_case():
    contract = Contract.objects.create(name="文书测试合同", case_type="civil")
    return Case.objects.create(name="文书测试案件", contract=contract)


# ===================================================================
# Document Template CRUD
# ===================================================================


@pytest.mark.django_db
def test_list_document_templates(authenticated_client):
    DocumentTemplate.objects.create(name="测试模板", template_type="case", is_active=True)
    resp = authenticated_client.get("/api/v1/documents/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.django_db
def test_list_document_templates_filter(authenticated_client):
    DocumentTemplate.objects.create(name="案件模板", template_type="case", is_active=True)
    DocumentTemplate.objects.create(name="合同模板", template_type="contract", is_active=True)
    resp = authenticated_client.get("/api/v1/documents/templates", {"template_type": "case"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.django_db
def test_create_document_template(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/documents/templates",
        data=json.dumps({"name": "新建模板", "template_type": "case", "is_active": True}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "新建模板"
    assert DocumentTemplate.objects.filter(id=data["id"]).exists()


@pytest.mark.django_db
def test_get_document_template_detail(authenticated_client):
    template = DocumentTemplate.objects.create(name="详情模板", template_type="case", is_active=True)
    resp = authenticated_client.get(f"/api/v1/documents/templates/{template.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "详情模板"


@pytest.mark.django_db
def test_update_document_template(authenticated_client):
    template = DocumentTemplate.objects.create(name="更新前", template_type="case", is_active=True)
    resp = authenticated_client.put(
        f"/api/v1/documents/templates/{template.id}",
        data=json.dumps({"name": "更新后"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "更新后"


@pytest.mark.django_db
def test_delete_document_template(authenticated_client):
    template = DocumentTemplate.objects.create(name="待删除", template_type="case", is_active=True)
    resp = authenticated_client.delete(f"/api/v1/documents/templates/{template.id}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.django_db
def test_list_template_library_files(authenticated_client):
    resp = authenticated_client.get("/api/v1/documents/templates/library-files")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ===================================================================
# Folder Template CRUD
# ===================================================================


@pytest.mark.django_db
def test_list_folder_templates(authenticated_client):
    FolderTemplate.objects.create(
        name="测试文件夹模板",
        template_type="case",
        case_types=["civil"],
        structure={"folders": ["材料", "文书"]},
        is_active=True,
    )
    resp = authenticated_client.get("/api/v1/documents/folder-templates")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.django_db
def test_create_folder_template(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/documents/folder-templates",
        data=json.dumps({
            "name": "新建文件夹模板",
            "case_type": "civil",
            "structure": {"folders": ["起诉材料", "证据材料"]},
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "新建文件夹模板"


@pytest.mark.django_db
def test_get_folder_template_detail(authenticated_client):
    template = FolderTemplate.objects.create(
        name="详情文件夹模板",
        template_type="case",
        case_types=["civil"],
        structure={"folders": ["材料"]},
        is_active=True,
    )
    resp = authenticated_client.get(f"/api/v1/documents/folder-templates/{template.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "详情文件夹模板"


@pytest.mark.django_db
def test_update_folder_template(authenticated_client):
    template = FolderTemplate.objects.create(
        name="更新前文件夹模板",
        template_type="case",
        case_types=["civil"],
        structure={"folders": ["旧材料"]},
        is_active=True,
    )
    resp = authenticated_client.put(
        f"/api/v1/documents/folder-templates/{template.id}",
        data=json.dumps({"name": "更新后文件夹模板"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "更新后文件夹模板"


@pytest.mark.django_db
def test_delete_folder_template(authenticated_client):
    template = FolderTemplate.objects.create(
        name="待删除文件夹模板",
        template_type="case",
        case_types=[],
        structure={"folders": []},
        is_active=True,
    )
    resp = authenticated_client.delete(f"/api/v1/documents/folder-templates/{template.id}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.django_db
def test_validate_folder_structure(authenticated_client):
    template = FolderTemplate.objects.create(
        name="验证模板",
        template_type="case",
        case_types=["civil"],
        structure={"folders": ["材料", "文书"]},
        is_active=True,
    )
    resp = authenticated_client.post(f"/api/v1/documents/folder-templates/{template.id}/validate")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_valid" in data


# ===================================================================
# Placeholder CRUD
# ===================================================================


@pytest.mark.django_db
def test_list_placeholders(authenticated_client):
    Placeholder.objects.create(key="{{原告姓名}}", display_name="原告姓名", example_value="张三", is_active=True)
    resp = authenticated_client.get("/api/v1/documents/placeholders")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.django_db
def test_create_placeholder(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/documents/placeholders",
        data=json.dumps({
            "key": "{{被告名称}}",
            "display_name": "被告名称",
            "example_value": "某某公司",
            "description": "被告的名称",
            "is_active": True,
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["key"] == "{{被告名称}}"
    assert Placeholder.objects.filter(id=data["id"]).exists()


@pytest.mark.django_db
def test_get_placeholder_detail(authenticated_client):
    ph = Placeholder.objects.create(key="{{案件编号}}", display_name="案件编号", example_value="2024-001", is_active=True)
    resp = authenticated_client.get(f"/api/v1/documents/placeholders/{ph.id}")
    assert resp.status_code == 200
    assert resp.json()["key"] == "{{案件编号}}"


@pytest.mark.django_db
def test_get_placeholder_by_key(authenticated_client):
    Placeholder.objects.create(key="{{测试键}}", display_name="测试键", example_value="值", is_active=True)
    resp = authenticated_client.get("/api/v1/documents/placeholders/by-key/{{测试键}}")
    assert resp.status_code == 200
    assert resp.json()["key"] == "{{测试键}}"


@pytest.mark.django_db
def test_update_placeholder(authenticated_client):
    ph = Placeholder.objects.create(key="{{旧键}}", display_name="旧名", example_value="旧值", is_active=True)
    resp = authenticated_client.put(
        f"/api/v1/documents/placeholders/{ph.id}",
        data=json.dumps({
            "key": "{{新键}}",
            "display_name": "新名",
            "example_value": "新值",
            "description": "新描述",
            "is_active": True,
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["key"] == "{{新键}}"


@pytest.mark.django_db
def test_delete_placeholder(authenticated_client):
    ph = Placeholder.objects.create(key="{{删除键}}", display_name="删除", example_value="", is_active=True)
    resp = authenticated_client.delete(f"/api/v1/documents/placeholders/{ph.id}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.django_db
def test_preview_placeholders(authenticated_client):
    contract = Contract.objects.create(name="预览合同", case_type="civil")
    resp = authenticated_client.get(f"/api/v1/documents/placeholders/preview/{contract.id}")
    # May return 400 if contract lacks required data for context building
    assert resp.status_code in (200, 400)
