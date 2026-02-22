"""
Bug 条件探索测试

验证 4 个 bug 修复后的行为正确。
代码已修复，这些测试应全部通过。

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8**
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from django.test import override_settings


# ============================================================
# Property 1: MEDIA_ROOT 优先级
# Validates: Requirements 1.1, 2.1
# ============================================================


def test_get_media_root_uses_settings_media_root(tmp_path: Path) -> None:
    """get_media_root() 应优先返回 settings.MEDIA_ROOT 的值"""
    from apps.client.services.id_card_merge.paths import get_media_root

    with override_settings(MEDIA_ROOT=str(tmp_path)):
        result = get_media_root()
        assert str(result) == str(tmp_path), (
            f"期望返回 {tmp_path}，实际返回 {result}"
        )


def test_get_media_root_fallback_when_empty(tmp_path: Path) -> None:
    """settings.MEDIA_ROOT 为空时应回退到 get_config"""
    from unittest.mock import patch

    from apps.client.services.id_card_merge.paths import get_media_root

    fallback_path = str(tmp_path / "fallback")
    Path(fallback_path).mkdir(parents=True, exist_ok=True)

    with override_settings(MEDIA_ROOT=""):
        with patch("apps.client.services.id_card_merge.paths.get_config", return_value=fallback_path):
            result = get_media_root()
            assert str(result) == fallback_path


# ============================================================
# Property 2: 4 个缺失端点应返回非 404 响应
# Validates: Requirements 1.2, 1.3, 1.4, 1.5, 2.2, 2.3, 2.4, 2.5
# ============================================================


@pytest.mark.django_db
def test_merge_id_card_endpoint_not_404() -> None:
    """POST /api/v1/client/identity-docs/merge-id-card 未认证应返回 401 而非 404"""
    from ninja.testing import TestClient

    from apps.client.api.clientidentitydoc_api import router

    client = TestClient(router)
    response = client.post("/identity-docs/merge-id-card", data={})
    assert response.status_code != 404, (
        f"端点不存在（404），实际状态码: {response.status_code}"
    )


@pytest.mark.django_db
def test_merge_id_card_manual_endpoint_not_404() -> None:
    """POST /api/v1/client/identity-docs/merge-id-card-manual 未认证应返回 401 而非 404"""
    from ninja.testing import TestClient

    from apps.client.api.clientidentitydoc_api import router

    client = TestClient(router)
    response = client.post("/identity-docs/merge-id-card-manual", data={})
    assert response.status_code != 404, (
        f"端点不存在（404），实际状态码: {response.status_code}"
    )


@pytest.mark.django_db
def test_recognize_submit_endpoint_not_404() -> None:
    """POST /api/v1/client/identity-doc/recognize/submit 未认证应返回 401 而非 404"""
    from ninja.testing import TestClient

    from apps.client.api.clientidentitydoc_api import router

    client = TestClient(router)
    response = client.post("/identity-doc/recognize/submit", data={})
    assert response.status_code != 404, (
        f"端点不存在（404），实际状态码: {response.status_code}"
    )


@pytest.mark.django_db
def test_task_status_endpoint_not_404() -> None:
    """GET /api/v1/client/identity-doc/task/{task_id} 未认证应返回 401 而非 404"""
    from ninja.testing import TestClient

    from apps.client.api.clientidentitydoc_api import router

    client = TestClient(router)
    response = client.get("/identity-doc/task/test-task-id-123")
    assert response.status_code != 404, (
        f"端点不存在（404），实际状态码: {response.status_code}"
    )


# ============================================================
# Property 3: 未认证请求应返回 401
# Validates: Requirements 1.6, 2.6
# ============================================================


def test_client_router_has_auth_configured() -> None:
    """验证 api.py 中 client router 已配置 JWTOrSessionAuth（检查源码配置）"""
    import ast
    from pathlib import Path

    import django
    from django.conf import settings

    # 通过 settings 模块文件定位项目根（backend/）
    settings_file = Path(django.__file__).parent  # django 包路径，用于确认 venv
    # settings 模块路径：backend/apiSystem/settings.py
    import apiSystem.settings as _settings_mod
    settings_dir = Path(_settings_mod.__file__).parent  # backend/apiSystem/
    api_file = settings_dir / "api.py"

    source = api_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found_auth = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "add_router":
                if node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "/client":
                    for kw in node.keywords:
                        if kw.arg == "auth":
                            found_auth = True
                            break

    assert found_auth, "api.py 中 client router 未配置 auth 参数，未认证请求将不会返回 401"


# ============================================================
# Property 4: rename_uploaded_file 对相对路径正确重命名
# Validates: Requirements 1.7, 1.8, 2.7, 2.8
# ============================================================


@pytest.mark.django_db
def test_rename_uploaded_file_relative_path(tmp_path: Path) -> None:
    """rename_uploaded_file 对相对路径应正确重命名，格式为 {doc_type}（{client_name}）.ext"""
    from apps.client.models import Client, ClientIdentityDoc
    from apps.client.services.client_identity_doc_service import ClientIdentityDocService

    # 创建临时文件（模拟相对路径结构）
    rel_dir = Path("client_docs") / "1"
    abs_dir = tmp_path / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    test_file = abs_dir / "license.pdf"
    test_file.write_bytes(b"fake pdf content")

    # 创建 Client 和 ClientIdentityDoc 实例
    client = Client.objects.create(
        name="广东润知信息科技有限公司",
        client_type=Client.LEGAL,
        legal_representative="张三",
    )
    doc = ClientIdentityDoc.objects.create(
        client=client,
        doc_type=ClientIdentityDoc.BUSINESS_LICENSE,
        file_path=str(rel_dir / "license.pdf"),  # 相对路径
    )

    service = ClientIdentityDocService()

    with override_settings(MEDIA_ROOT=str(tmp_path)):
        service.rename_uploaded_file(doc)

    # 验证文件名格式为 {doc_type}（{client_name}）.ext
    new_filename = Path(doc.file_path).name
    assert new_filename == "营业执照（广东润知信息科技有限公司）.pdf", (
        f"文件名格式错误，期望 '营业执照（广东润知信息科技有限公司）.pdf'，实际 '{new_filename}'"
    )

    # 验证保存的是相对路径
    assert not Path(doc.file_path).is_absolute(), (
        f"应保存相对路径，实际保存了绝对路径: {doc.file_path}"
    )

    # 清理
    shutil.rmtree(str(abs_dir), ignore_errors=True)


@pytest.mark.django_db
def test_rename_uploaded_file_absolute_path(tmp_path: Path) -> None:
    """rename_uploaded_file 对绝对路径也应正确重命名（回归防护）"""
    from apps.client.models import Client, ClientIdentityDoc
    from apps.client.services.client_identity_doc_service import ClientIdentityDocService

    # 创建临时文件（绝对路径）
    abs_dir = tmp_path / "client_docs" / "2"
    abs_dir.mkdir(parents=True, exist_ok=True)
    test_file = abs_dir / "id.jpg"
    test_file.write_bytes(b"fake image content")

    client = Client.objects.create(
        name="张三",
        client_type=Client.NATURAL,
    )
    doc = ClientIdentityDoc.objects.create(
        client=client,
        doc_type=ClientIdentityDoc.ID_CARD,
        file_path=str(test_file),  # 绝对路径
    )

    service = ClientIdentityDocService()

    with override_settings(MEDIA_ROOT=str(tmp_path)):
        service.rename_uploaded_file(doc)

    new_filename = Path(doc.file_path).name
    assert new_filename == "身份证（张三）.jpg", (
        f"文件名格式错误，期望 '身份证（张三）.jpg'，实际 '{new_filename}'"
    )
