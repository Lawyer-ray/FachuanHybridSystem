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

    with override_settings(MEDIA_ROOT=""):
        with patch("apps.client.services.storage.get_config", return_value=fallback):
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
