"""
保全属性测试

验证已有功能在修复后仍然正常工作。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15, 3.16**
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st


# ============================================================
# 1. storage.py 的 _get_media_root() 行为不变
# Validates: Requirements 3.1, 3.6
# ============================================================


def test_storage_get_media_root_prefers_settings(tmp_path: object) -> None:
    """_get_media_root() 优先读取 settings.MEDIA_ROOT"""
    from pathlib import Path

    tmp = Path(str(tmp_path))  # type: ignore[arg-type]
    from apps.client.services.storage import _get_media_root

    with override_settings(MEDIA_ROOT=str(tmp)):
        result = _get_media_root()
        assert result == str(tmp)


def test_storage_get_media_root_fallback(tmp_path: object) -> None:
    """settings.MEDIA_ROOT 为空时回退到 get_config"""
    from pathlib import Path
    from unittest.mock import patch

    fallback = str(Path(str(tmp_path)) / "fallback")  # type: ignore[arg-type]

    from apps.client.services.storage import _get_media_root

    with override_settings(MEDIA_ROOT=""), patch("apps.client.services.storage.get_config", return_value=fallback):
        result = _get_media_root()
        assert result == fallback


# ============================================================
# 2. 已有端点正常工作（非 404）
# Validates: Requirements 3.3
# ============================================================


@pytest.mark.django_db
def test_existing_endpoint_recognize_not_404() -> None:
    """/identity-doc/recognize 端点存在（非 404）"""
    from ninja.testing import TestClient

    from apps.client.api.clientidentitydoc_api import router

    client = TestClient(router)
    response = client.post("/identity-doc/recognize", data={})
    assert response.status_code != 404, f"端点不存在，状态码: {response.status_code}"


@pytest.mark.django_db
def test_existing_endpoint_identity_docs_not_404() -> None:
    """/clients/{client_id}/identity-docs 端点存在（非 404）"""
    from ninja.testing import TestClient

    from apps.client.api.clientidentitydoc_api import router

    client = TestClient(router)
    response = client.post("/clients/1/identity-docs", data={})
    assert response.status_code != 404, f"端点不存在，状态码: {response.status_code}"


def test_existing_endpoint_identity_doc_detail_registered() -> None:
    """/identity-docs/{doc_id} 端点已注册（路由存在）"""
    import inspect

    from apps.client.api import clientidentitydoc_api

    source = inspect.getsource(clientidentitydoc_api)
    assert "/identity-docs/{doc_id}" in source, (
        "路由 /identity-docs/{doc_id} 未在 clientidentitydoc_api.py 中注册"
    )


@pytest.mark.django_db
def test_existing_endpoint_parse_text_not_404() -> None:
    """/parse-text 端点存在（非 404）"""
    from ninja.testing import TestClient

    from apps.client.api.clientidentitydoc_api import router

    client = TestClient(router)
    response = client.get("/parse-text")
    assert response.status_code != 404, f"端点不存在，状态码: {response.status_code}"


# ============================================================
# 3. sanitize_upload_filename 正确清理文件名
# Validates: Requirements 3.5, 3.10
# ============================================================


def test_sanitize_upload_filename_removes_illegal_chars() -> None:
    """sanitize_upload_filename 清理非法字符"""
    from apps.client.services.storage import sanitize_upload_filename

    result = sanitize_upload_filename("hello world!@#.pdf")
    assert "/" not in result
    assert "\\" not in result
    assert result.endswith(".pdf")


def test_sanitize_upload_filename_preserves_chinese() -> None:
    """sanitize_upload_filename 保留中文字符"""
    from apps.client.services.storage import sanitize_upload_filename

    result = sanitize_upload_filename("营业执照.pdf")
    assert "营业执照" in result
    assert result.endswith(".pdf")


def test_sanitize_upload_filename_handles_empty() -> None:
    """sanitize_upload_filename 处理空字符串"""
    from apps.client.services.storage import sanitize_upload_filename

    result = sanitize_upload_filename("")
    assert result  # 不为空
    assert len(result) > 0


def test_sanitize_upload_filename_max_length() -> None:
    """sanitize_upload_filename 限制最大长度"""
    from apps.client.services.storage import sanitize_upload_filename

    long_name = "a" * 200 + ".pdf"
    result = sanitize_upload_filename(long_name, max_length=120)
    assert len(result) <= 120


@given(
    filename=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd", "Lo"),
            whitelist_characters="._- !@#$%^&*()",
        ),
        min_size=0,
        max_size=50,
    )
)
@h_settings(max_examples=100)
def test_sanitize_upload_filename_property(filename: str) -> None:
    """
    属性测试：sanitize_upload_filename 对任意输入都返回合法文件名

    **Validates: Requirements 3.5, 3.10**
    """
    from apps.client.services.storage import sanitize_upload_filename

    result = sanitize_upload_filename(filename)
    # 结果不为空
    assert result
    # 不含路径分隔符
    assert "/" not in result
    assert "\\" not in result
    # 长度不超过默认最大值
    assert len(result) <= 120


# ============================================================
# 4. models/ 目录中所有 Model 正常加载
# Validates: Requirements 3.7
# ============================================================


def test_client_model_importable() -> None:
    """Client 模型可正常导入"""
    from apps.client.models import Client

    assert Client is not None
    assert hasattr(Client, "objects")


def test_client_identity_doc_model_importable() -> None:
    """ClientIdentityDoc 模型可正常导入"""
    from apps.client.models import ClientIdentityDoc

    assert ClientIdentityDoc is not None
    assert hasattr(ClientIdentityDoc, "objects")


def test_property_clue_model_importable() -> None:
    """PropertyClue 模型可正常导入"""
    from apps.client.models import PropertyClue

    assert PropertyClue is not None
    assert hasattr(PropertyClue, "objects")


def test_property_clue_attachment_model_importable() -> None:
    """PropertyClueAttachment 模型可正常导入"""
    from apps.client.models import PropertyClueAttachment

    assert PropertyClueAttachment is not None
    assert hasattr(PropertyClueAttachment, "objects")


@pytest.mark.django_db
def test_client_model_has_required_fields() -> None:
    """Client 模型包含必要字段"""
    from apps.client.models import Client

    field_names = [f.name for f in Client._meta.get_fields()]
    assert "name" in field_names
    assert "client_type" in field_names


# ============================================================
# 5. ClientMutationService 的 CRUD 操作正常
# Validates: Requirements 3.8
# ============================================================


def test_client_mutation_service_has_create_client() -> None:
    """ClientMutationService 有 create_client 方法"""
    from apps.client.services.client_mutation_service import ClientMutationService

    svc = ClientMutationService()
    assert callable(getattr(svc, "create_client", None))


def test_client_mutation_service_has_update_client() -> None:
    """ClientMutationService 有 update_client 方法"""
    from apps.client.services.client_mutation_service import ClientMutationService

    svc = ClientMutationService()
    assert callable(getattr(svc, "update_client", None))


def test_client_mutation_service_has_delete_client() -> None:
    """ClientMutationService 有 delete_client 方法"""
    from apps.client.services.client_mutation_service import ClientMutationService

    svc = ClientMutationService()
    assert callable(getattr(svc, "delete_client", None))


# ============================================================
# 6. ClientServiceAdapter 从正确位置导入
# Validates: Requirements 3.9
# ============================================================


def test_client_service_adapter_exported_from_services_init() -> None:
    """services/__init__.py 导出 ClientServiceAdapter"""
    from apps.client import services

    assert hasattr(services, "ClientServiceAdapter")


def test_client_service_adapter_is_full_version() -> None:
    """services/__init__.py 导出的是 client_service_adapter.py 中的完整版本"""
    from apps.client.services import ClientServiceAdapter
    from apps.client.services.client_service_adapter import ClientServiceAdapter as FullAdapter

    assert ClientServiceAdapter is FullAdapter, (
        "services/__init__.py 导出的 ClientServiceAdapter 不是 client_service_adapter.py 中的完整版本"
    )


def test_client_service_adapter_has_full_methods() -> None:
    """ClientServiceAdapter 包含完整方法集"""
    from apps.client.services import ClientServiceAdapter

    expected_methods = [
        "get_client",
        "get_client_internal",
        "get_clients_by_ids",
        "validate_client_exists",
        "get_client_by_name",
        "get_all_clients_internal",
        "search_clients_by_name_internal",
        "get_property_clues_by_client_internal",
        "is_natural_person_internal",
        "get_identity_docs_by_client_internal",
    ]
    for method in expected_methods:
        assert callable(getattr(ClientServiceAdapter, method, None)), (
            f"ClientServiceAdapter 缺少方法: {method}"
        )


# ============================================================
# Task 2 Preservation Tests (client-module-fixes-v2)
# 验证修复前后行为一致的基线
# Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
# ============================================================


# ---- Test 2a: add_identity_doc 创建证件记录 ----

@pytest.mark.django_db
def test_2a_add_identity_doc_creates_record(tmp_path: object) -> None:
    """
    add_identity_doc() 创建证件记录并自动重命名文件。

    **Validates: Requirements 3.1, 3.2**
    """
    from pathlib import Path
    from unittest.mock import patch

    from django.test import override_settings

    from apps.client.models import Client, ClientIdentityDoc
    from apps.client.services.client_identity_doc_service import ClientIdentityDocService

    tmp = Path(str(tmp_path))  # type: ignore[arg-type]
    # 创建测试客户
    client = Client.objects.create(name="测试客户", client_type="natural")

    # 创建一个临时文件模拟上传
    fake_file = tmp / "test.jpg"
    fake_file.write_bytes(b"fake image content")

    with override_settings(MEDIA_ROOT=str(tmp)):
        svc = ClientIdentityDocService()
        doc = svc.add_identity_doc(
            client_id=client.id,
            doc_type="id_card",
            file_path=str(fake_file),
        )

    assert doc.pk is not None
    assert doc.client_id == client.id
    assert doc.doc_type == "id_card"
    # 记录已持久化
    assert ClientIdentityDoc.objects.filter(pk=doc.pk).exists()


@pytest.mark.django_db
def test_2a_add_identity_doc_raises_not_found_for_missing_client() -> None:
    """add_identity_doc() 当事人不存在时抛出 NotFoundError。"""
    from apps.core.exceptions import NotFoundError
    from apps.client.services.client_identity_doc_service import ClientIdentityDocService

    svc = ClientIdentityDocService()
    with pytest.raises(NotFoundError):
        svc.add_identity_doc(client_id=999999, doc_type="id_card", file_path="x.jpg")


# ---- Test 2b: rename_uploaded_file 按标准格式重命名 ----

@pytest.mark.django_db
def test_2b_rename_uploaded_file_renames_correctly(tmp_path: object) -> None:
    """
    rename_uploaded_file() 按 {doc_type_display}（{client_name}）.ext 格式重命名。

    **Validates: Requirements 3.2**
    """
    from pathlib import Path

    from django.test import override_settings

    from apps.client.models import Client, ClientIdentityDoc
    from apps.client.services.client_identity_doc_service import ClientIdentityDocService

    tmp = Path(str(tmp_path))  # type: ignore[arg-type]
    client = Client.objects.create(name="张三", client_type="natural")

    # 创建原始文件
    original = tmp / "upload_abc123.jpg"
    original.write_bytes(b"fake")

    with override_settings(MEDIA_ROOT=str(tmp)):
        doc = ClientIdentityDoc.objects.create(
            client=client,
            doc_type="id_card",
            file_path=str(original.relative_to(tmp)),
        )
        svc = ClientIdentityDocService()
        svc.rename_uploaded_file(doc)

    # 文件名应包含客户名
    assert "张三" in doc.file_path or "张三" in str(doc.file_path)


@pytest.mark.django_db
def test_2b_rename_uploaded_file_noop_when_no_file(tmp_path: object) -> None:
    """rename_uploaded_file() 文件路径为空时不报错。"""
    from apps.client.models import Client, ClientIdentityDoc
    from apps.client.services.client_identity_doc_service import ClientIdentityDocService

    client = Client.objects.create(name="李四", client_type="natural")
    doc = ClientIdentityDoc.objects.create(client=client, doc_type="id_card", file_path="")

    svc = ClientIdentityDocService()
    svc.rename_uploaded_file(doc)  # 不应抛出异常


# ---- Test 2c: IdCardMergeService 合并身份证（mock 文件 IO）----

def test_2c_idcard_merge_service_returns_success_structure() -> None:
    """
    IdCardMergeService.merge_id_card() 成功时返回含 pdf_path 和 pdf_url 的字典。

    **Validates: Requirements 3.3**
    """
    from unittest.mock import MagicMock, patch

    from apps.client.services.id_card_merge.facade import IdCardMergeService

    svc = IdCardMergeService()

    mock_file = MagicMock()
    mock_file.name = "test.jpg"
    mock_file.content_type = "image/jpeg"

    with patch.object(svc, "_validate_image_format", return_value=None), \
         patch.object(svc, "_read_uploaded_image", return_value=MagicMock()), \
         patch.object(svc, "_validate_image_size", return_value=None), \
         patch.object(svc, "_generate_pdf", return_value="id_card_pdfs/output.pdf"):
        result = svc.merge_id_card(mock_file, mock_file)

    assert result["success"] is True
    assert "pdf_path" in result
    assert "pdf_url" in result
    assert result["pdf_path"] == "id_card_pdfs/output.pdf"
    assert "/media/" in result["pdf_url"]


def test_2c_idcard_merge_service_returns_error_on_invalid_format() -> None:
    """IdCardMergeService.merge_id_card() 格式验证失败时返回错误结构。"""
    from unittest.mock import MagicMock, patch

    from apps.client.services.id_card_merge.facade import IdCardMergeService

    svc = IdCardMergeService()
    mock_file = MagicMock()
    mock_file.name = "test.bmp"
    mock_file.content_type = "image/bmp"

    error_result = {"success": False, "error": "INVALID_FORMAT", "message": "不支持的格式"}
    with patch.object(svc, "_validate_image_format", return_value=error_result):
        result = svc.merge_id_card(mock_file, mock_file)

    assert result["success"] is False
    assert "error" in result


# ---- Test 2d: PropertyClueService CRUD ----

@pytest.mark.django_db
def test_2d_property_clue_service_create_and_get() -> None:
    """
    PropertyClueService.create_clue() 创建线索，get_clue() 可查询。

    **Validates: Requirements 3.4**
    """
    from apps.client.models import Client
    from apps.client.services.property_clue_service import PropertyClueService

    client = Client.objects.create(name="王五", client_type="natural")
    svc = PropertyClueService()

    clue = svc.create_clue(client_id=client.id, data={"clue_type": "bank", "content": "工商银行"})
    assert clue.pk is not None
    assert clue.content == "工商银行"

    fetched = svc.get_clue(clue.pk)
    assert fetched.pk == clue.pk


@pytest.mark.django_db
def test_2d_property_clue_service_update() -> None:
    """PropertyClueService.update_clue() 更新线索内容。"""
    from apps.client.models import Client
    from apps.client.services.property_clue_service import PropertyClueService

    client = Client.objects.create(name="赵六", client_type="natural")
    svc = PropertyClueService()
    clue = svc.create_clue(client_id=client.id, data={"clue_type": "bank", "content": "原内容"})

    updated = svc.update_clue(clue.pk, data={"content": "新内容"})
    assert updated.content == "新内容"


@pytest.mark.django_db
def test_2d_property_clue_service_delete() -> None:
    """PropertyClueService.delete_clue() 删除线索。"""
    from apps.client.models import Client, PropertyClue
    from apps.client.services.property_clue_service import PropertyClueService

    client = Client.objects.create(name="孙七", client_type="natural")
    svc = PropertyClueService()
    clue = svc.create_clue(client_id=client.id, data={"clue_type": "bank", "content": "待删除"})
    clue_id = clue.pk

    svc.delete_clue(clue_id)
    assert not PropertyClue.objects.filter(pk=clue_id).exists()


@pytest.mark.django_db
def test_2d_property_clue_service_list_by_client() -> None:
    """PropertyClueService.list_clues_by_client() 返回该客户的所有线索。"""
    from apps.client.models import Client
    from apps.client.services.property_clue_service import PropertyClueService

    client = Client.objects.create(name="周八", client_type="natural")
    svc = PropertyClueService()
    svc.create_clue(client_id=client.id, data={"clue_type": "bank", "content": "线索1"})
    svc.create_clue(client_id=client.id, data={"clue_type": "real_estate", "content": "线索2"})

    clues = svc.list_clues_by_client(client_id=client.id)
    assert len(clues) == 2


# ---- Test 2e: ClientDtoAssembler.to_dto() 返回完整 DTO ----

@pytest.mark.django_db
def test_2e_client_dto_assembler_returns_complete_dto() -> None:
    """
    ClientDtoAssembler.to_dto() 返回包含所有字段的 ClientDTO。

    **Validates: Requirements 3.6**
    """
    from apps.client.models import Client
    from apps.client.services.client_dto_assembler import ClientDtoAssembler
    from apps.core.interfaces import ClientDTO

    client = Client.objects.create(
        name="测试法人",
        client_type="legal",
        phone="13800138000",
        id_number="91110000123456789X",
        address="北京市朝阳区",
        is_our_client=True,
    )

    assembler = ClientDtoAssembler()
    dto = assembler.to_dto(client)

    assert isinstance(dto, ClientDTO)
    assert dto.id == client.id
    assert dto.name == "测试法人"
    assert dto.client_type == "legal"
    assert dto.phone == "13800138000"
    assert dto.id_number == "91110000123456789X"
    assert dto.address == "北京市朝阳区"
    assert dto.is_our_client is True


@pytest.mark.django_db
def test_2e_client_dto_assembler_handles_null_fields() -> None:
    """ClientDtoAssembler.to_dto() 处理可选字段为 None 的情况。"""
    from apps.client.models import Client
    from apps.client.services.client_dto_assembler import ClientDtoAssembler

    client = Client.objects.create(name="最简客户", client_type="natural")

    assembler = ClientDtoAssembler()
    dto = assembler.to_dto(client)

    assert dto.id == client.id
    assert dto.name == "最简客户"


# ---- Test 2f: ClientAdminService.import_from_json() 正确创建客户 ----

@pytest.mark.django_db
def test_2f_import_from_json_creates_client(tmp_path: object) -> None:
    """
    ClientAdminService.import_from_json() 正确创建客户。

    **Validates: Requirements 3.7**
    """
    from pathlib import Path

    from django.test import override_settings

    from apps.client.models import Client
    from apps.client.services.client_admin_service import ClientAdminService

    tmp = Path(str(tmp_path))  # type: ignore[arg-type]

    json_data = {
        "name": "JSON导入客户",
        "client_type": "natural",
        "phone": "13900139000",
    }

    with override_settings(MEDIA_ROOT=str(tmp)):
        svc = ClientAdminService()
        result = svc.import_from_json(json_data, admin_user="admin")

    assert result.success is True
    assert result.client is not None
    assert result.client.name == "JSON导入客户"
    assert Client.objects.filter(name="JSON导入客户").exists()


@pytest.mark.django_db
def test_2f_import_from_json_creates_identity_docs(tmp_path: object) -> None:
    """ClientAdminService.import_from_json() 同时创建关联证件。"""
    from pathlib import Path

    from django.test import override_settings

    from apps.client.models import ClientIdentityDoc
    from apps.client.services.client_admin_service import ClientAdminService

    tmp = Path(str(tmp_path))  # type: ignore[arg-type]
    fake_file = tmp / "doc.jpg"
    fake_file.write_bytes(b"fake")

    json_data = {
        "name": "带证件客户",
        "client_type": "natural",
        "identity_docs": [
            {"doc_type": "id_card", "file_path": str(fake_file)},
        ],
    }

    with override_settings(MEDIA_ROOT=str(tmp)):
        svc = ClientAdminService()
        result = svc.import_from_json(json_data, admin_user="admin")

    assert result.success is True
    assert result.client is not None
    assert ClientIdentityDoc.objects.filter(client=result.client).count() == 1


@pytest.mark.django_db
def test_2f_import_from_json_fails_on_invalid_data() -> None:
    """ClientAdminService.import_from_json() 数据无效时返回失败或抛出 ValidationException。"""
    from apps.client.services.client_admin_service import ClientAdminService
    from apps.core.exceptions import ValidationException

    svc = ClientAdminService()
    with pytest.raises(ValidationException):
        svc.import_from_json({"name": ""}, admin_user="admin")


# ---- Test 2g: ClientServiceAdapter 各方法正确转换 DTO ----

@pytest.mark.django_db
def test_2g_client_service_adapter_get_client_returns_dto() -> None:
    """
    ClientServiceAdapter.get_client() 返回 ClientDTO。

    **Validates: Requirements 3.8**
    """
    from apps.client.models import Client
    from apps.client.services.client_service_adapter import ClientServiceAdapter
    from apps.core.interfaces import ClientDTO

    client = Client.objects.create(name="适配器测试", client_type="natural")

    adapter = ClientServiceAdapter()
    dto = adapter.get_client(client.id)

    assert dto is not None
    assert isinstance(dto, ClientDTO)
    assert dto.id == client.id
    assert dto.name == "适配器测试"


@pytest.mark.django_db
def test_2g_client_service_adapter_get_client_returns_none_for_missing() -> None:
    """ClientServiceAdapter.get_client() 不存在时返回 None。"""
    from apps.client.services.client_service_adapter import ClientServiceAdapter

    adapter = ClientServiceAdapter()
    result = adapter.get_client(999999)
    assert result is None


@pytest.mark.django_db
def test_2g_client_service_adapter_get_clients_by_ids() -> None:
    """ClientServiceAdapter.get_clients_by_ids() 批量返回 DTO 列表。"""
    from apps.client.models import Client
    from apps.client.services.client_service_adapter import ClientServiceAdapter

    c1 = Client.objects.create(name="批量1", client_type="natural")
    c2 = Client.objects.create(name="批量2", client_type="natural")

    adapter = ClientServiceAdapter()
    dtos = adapter.get_clients_by_ids([c1.id, c2.id])

    assert len(dtos) == 2
    names = {d.name for d in dtos}
    assert "批量1" in names
    assert "批量2" in names


@pytest.mark.django_db
def test_2g_client_service_adapter_validate_client_exists() -> None:
    """ClientServiceAdapter.validate_client_exists() 正确判断存在性。"""
    from apps.client.models import Client
    from apps.client.services.client_service_adapter import ClientServiceAdapter

    client = Client.objects.create(name="存在性测试", client_type="natural")
    adapter = ClientServiceAdapter()

    assert adapter.validate_client_exists(client.id) is True
    assert adapter.validate_client_exists(999999) is False


@pytest.mark.django_db
def test_2g_client_service_adapter_get_identity_docs_by_client() -> None:
    """ClientServiceAdapter.get_identity_docs_by_client_internal() 返回证件 DTO 列表。"""
    from pathlib import Path

    from apps.client.models import Client, ClientIdentityDoc
    from apps.client.services.client_service_adapter import ClientServiceAdapter

    client = Client.objects.create(name="证件适配器测试", client_type="natural")
    ClientIdentityDoc.objects.create(client=client, doc_type="id_card", file_path="test.jpg")

    adapter = ClientServiceAdapter()
    docs = adapter.get_identity_docs_by_client_internal(client.id)

    assert len(docs) == 1
    assert docs[0].doc_type == "id_card"
