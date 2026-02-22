"""
Bug Condition Exploration Tests - Client 模块第二轮审计

这些测试编码的是"期望行为"（修复后的正确状态）。
在未修复代码上运行时，测试会 FAIL，证明 bug 存在。
修复完成后，测试会 PASS，确认 bug 已修复。

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11**
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

# 项目根目录（backend/）
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent


# ---------------------------------------------------------------------------
# Test 1a: ClientIdentityDocService 应有 get_identity_doc 方法
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_1a_get_identity_doc_method_exists() -> None:
    """
    期望行为：ClientIdentityDocService 应提供 get_identity_doc() 方法。
    未修复时 FAIL（AttributeError），修复后 PASS。

    Validates: Requirements 1.1
    """
    from apps.client.services.client_identity_doc_service import ClientIdentityDocService

    service = ClientIdentityDocService()
    assert hasattr(service, "get_identity_doc"), (
        "BUG 1.1: ClientIdentityDocService 缺少 get_identity_doc() 方法，"
        "调用 GET /identity-docs/{id} 时会抛出 AttributeError"
    )


# ---------------------------------------------------------------------------
# Test 1b: ClientIdentityDocService 应有 delete_identity_doc 方法
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_1b_delete_identity_doc_method_exists() -> None:
    """
    期望行为：ClientIdentityDocService 应提供 delete_identity_doc() 方法。
    未修复时 FAIL（AttributeError），修复后 PASS。

    Validates: Requirements 1.2
    """
    from apps.client.services.client_identity_doc_service import ClientIdentityDocService

    service = ClientIdentityDocService()
    assert hasattr(service, "delete_identity_doc"), (
        "BUG 1.2: ClientIdentityDocService 缺少 delete_identity_doc() 方法，"
        "调用 DELETE /identity-docs/{id} 时会抛出 AttributeError"
    )


# ---------------------------------------------------------------------------
# Test 1c: clientidentitydoc_admin.py 不应直接导入 save_uploaded_file
# ---------------------------------------------------------------------------
def test_1c_clientidentitydoc_admin_no_direct_save_uploaded_file() -> None:
    """
    期望行为：ClientIdentityDocForm.save() 不应直接调用 save_uploaded_file，
    应委托 Service 层处理文件 IO。
    未修复时 FAIL，修复后 PASS。

    Validates: Requirements 1.3
    """
    admin_file = BACKEND_DIR / "apps" / "client" / "admin" / "clientidentitydoc_admin.py"
    source = admin_file.read_text(encoding="utf-8")

    assert "from apps.client.services.storage import save_uploaded_file" not in source, (
        "BUG 1.3: clientidentitydoc_admin.py 中 ClientIdentityDocForm.save() "
        "直接导入并调用 save_uploaded_file，违反四层架构规范（Admin 层不应直接做文件 IO）"
    )


# ---------------------------------------------------------------------------
# Test 1d: property_clue_admin.py 不应直接导入 save_uploaded_file
# ---------------------------------------------------------------------------
def test_1d_property_clue_admin_no_direct_save_uploaded_file() -> None:
    """
    期望行为：PropertyClueAttachmentInlineForm.save() 不应直接调用 save_uploaded_file，
    应委托 Service 层处理文件 IO。
    未修复时 FAIL，修复后 PASS。

    Validates: Requirements 1.4
    """
    admin_file = BACKEND_DIR / "apps" / "client" / "admin" / "property_clue_admin.py"
    source = admin_file.read_text(encoding="utf-8")

    assert "from apps.client.services.storage import save_uploaded_file" not in source, (
        "BUG 1.4: property_clue_admin.py 中 PropertyClueAttachmentInlineForm.save() "
        "直接导入并调用 save_uploaded_file，违反四层架构规范（Admin 层不应直接做文件 IO）"
    )


# ---------------------------------------------------------------------------
# Test 1e: facade.py / client_admin.py / client_admin_service.py 不应有 f-string logger
# ---------------------------------------------------------------------------
def test_1e_no_fstring_logger_in_facade() -> None:
    """
    期望行为：facade.py 中 logger 调用应使用 %s 占位符，不应使用 f-string。
    未修复时 FAIL，修复后 PASS。

    Validates: Requirements 1.5
    """
    facade_file = BACKEND_DIR / "apps" / "client" / "services" / "id_card_merge" / "facade.py"
    source = facade_file.read_text(encoding="utf-8")

    # 检查是否存在 logger.xxx(f"..." 模式
    import re
    fstring_logger_pattern = re.compile(r'logger\.\w+\(\s*f["\']', re.MULTILINE)
    matches = fstring_logger_pattern.findall(source)

    assert not matches, (
        f"BUG 1.5: facade.py 中存在 {len(matches)} 处 f-string logger 调用: {matches}。"
        "应使用 %s 占位符替代 f-string"
    )


def test_1e_no_fstring_logger_in_client_admin() -> None:
    """
    期望行为：client_admin.py 中 logger 调用应使用 %s 占位符，不应使用 f-string。
    未修复时 FAIL，修复后 PASS。

    Validates: Requirements 1.6
    """
    admin_file = BACKEND_DIR / "apps" / "client" / "admin" / "client_admin.py"
    source = admin_file.read_text(encoding="utf-8")

    import re
    fstring_logger_pattern = re.compile(r'logger\.\w+\(\s*f["\']', re.MULTILINE)
    matches = fstring_logger_pattern.findall(source)

    assert not matches, (
        f"BUG 1.6: client_admin.py 中存在 {len(matches)} 处 f-string logger 调用: {matches}。"
        "应使用 %s 占位符替代 f-string"
    )


def test_1e_no_fstring_logger_in_client_admin_service() -> None:
    """
    期望行为：client_admin_service.py 中 logger 调用应使用 %s 占位符，不应使用 f-string。
    未修复时 FAIL，修复后 PASS。

    Validates: Requirements 1.7
    """
    import re
    service_file = BACKEND_DIR / "apps" / "client" / "services" / "client_admin_service.py"
    source = service_file.read_text(encoding="utf-8")

    # 匹配 logger.xxx( 后紧跟 f" 或 f'（含换行情况）
    fstring_logger_pattern = re.compile(r'logger\.\w+\(\s*f["\']', re.MULTILINE)
    matches = fstring_logger_pattern.findall(source)

    assert not matches, (
        f"BUG 1.7: client_admin_service.py 中存在 {len(matches)} 处 f-string logger 调用: {matches}。"
        "应使用 %s 占位符替代 f-string"
    )


# ---------------------------------------------------------------------------
# Test 1f: client_dto_assembler.py 不应有 cast / type: ignore / hasattr
# ---------------------------------------------------------------------------
def test_1f_client_dto_assembler_no_cast_type_ignore_hasattr() -> None:
    """
    期望行为：client_dto_assembler.py 中 to_dto() 应直接使用 client.id，
    不应使用 cast、# type: ignore 或 hasattr。
    未修复时 FAIL，修复后 PASS。

    Validates: Requirements 1.8
    """
    assembler_file = BACKEND_DIR / "apps" / "client" / "services" / "client_dto_assembler.py"
    source = assembler_file.read_text(encoding="utf-8")

    issues = []
    if "cast(" in source:
        issues.append("使用了 cast()")
    if "# type: ignore" in source:
        issues.append("使用了 # type: ignore")
    if "hasattr(" in source:
        issues.append("使用了 hasattr()")

    assert not issues, (
        f"BUG 1.8: client_dto_assembler.py 中存在类型注解问题: {', '.join(issues)}。"
        "应直接使用 client.id，移除 cast/type: ignore/hasattr"
    )


# ---------------------------------------------------------------------------
# Test 1g: property_clue_service.py 不应有 # type: ignore
# ---------------------------------------------------------------------------
def test_1g_property_clue_service_no_type_ignore() -> None:
    """
    期望行为：property_clue_service.py 中方法签名应使用 Any 类型，
    不应有 # type: ignore 注释。
    未修复时 FAIL，修复后 PASS。

    Validates: Requirements 1.9
    """
    service_file = BACKEND_DIR / "apps" / "client" / "services" / "property_clue_service.py"
    source = service_file.read_text(encoding="utf-8")

    import re
    # 统计 # type: ignore 出现次数
    type_ignore_count = len(re.findall(r'#\s*type:\s*ignore', source))

    assert type_ignore_count == 0, (
        f"BUG 1.9: property_clue_service.py 中存在 {type_ignore_count} 处 # type: ignore 注释。"
        "应将 user 参数类型改为 Any，移除所有 # type: ignore"
    )


# ---------------------------------------------------------------------------
# Test 1h: 4 个文件的模块文档字符串不应为 "External service client."
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel_path,expected_docstring_hint", [
    (
        "apps/client/services/client_internal_query_service.py",
        "当事人内部查询服务",
    ),
    (
        "apps/client/services/client_service_adapter.py",
        "当事人服务适配器",
    ),
    (
        "apps/client/services/client_related_dto_assembler.py",
        "当事人关联 DTO 组装器",
    ),
    (
        "apps/client/services/client_dto_assembler.py",
        "当事人 DTO 组装器",
    ),
])
def test_1h_module_docstring_not_external_service_client(rel_path: str, expected_docstring_hint: str) -> None:
    """
    期望行为：4 个文件的模块文档字符串应与各自职责匹配，
    不应为复制粘贴的 "External service client."。
    未修复时 FAIL，修复后 PASS。

    Validates: Requirements 1.10
    """
    target_file = BACKEND_DIR / rel_path
    source = target_file.read_text(encoding="utf-8")

    assert 'External service client.' not in source, (
        f"BUG 1.10: {rel_path} 的模块文档字符串为 'External service client.'，"
        f"应改为描述实际职责（如包含 '{expected_docstring_hint}'）"
    )


# ---------------------------------------------------------------------------
# Test 1i: client_admin_service.py 中 _process_single_form 不应直接调用 Client.objects / ClientIdentityDoc.objects.create
# ---------------------------------------------------------------------------
def test_1i_process_single_form_no_direct_model_objects() -> None:
    """
    期望行为：_process_single_form() 应通过 ClientInternalQueryService 查询 Client，
    通过 ClientIdentityDocService 创建证件记录，不应直接调用 Client.objects 或
    ClientIdentityDoc.objects.create。
    未修复时 FAIL，修复后 PASS。

    Validates: Requirements 1.11
    """
    from apps.client.services.client_admin_service import ClientAdminService

    # 获取 _process_single_form 方法的源码
    method_source = inspect.getsource(ClientAdminService._process_single_form)

    issues = []
    if "Client.objects" in method_source:
        issues.append("直接调用 Client.objects")
    if "ClientIdentityDoc.objects.create" in method_source:
        issues.append("直接调用 ClientIdentityDoc.objects.create")

    assert not issues, (
        f"BUG 1.11: _process_single_form() 中存在直接 Model.objects 调用: {', '.join(issues)}。"
        "应通过 ClientInternalQueryService 查询 Client，"
        "通过 ClientIdentityDocService 创建证件记录"
    )
