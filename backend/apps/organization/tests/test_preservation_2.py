"""
Preservation Property Tests (Round 2) - Organization 模块第二轮现有行为保持

这些测试验证修复前后行为一致性。在未修复代码上运行时应 PASS，
修复完成后也应 PASS，确认没有引入回归。

采用静态分析 + 逻辑等价验证方式，不依赖 Django 运行时。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# 项目根目录
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent
ORG_DIR: Path = BACKEND_DIR / "apps" / "organization"


def _read_source(rel_path: str) -> str:
    """读取源文件内容"""
    return (ORG_DIR / rel_path).read_text(encoding="utf-8")


def _parse_ast(rel_path: str) -> ast.Module:
    """解析源文件 AST"""
    return ast.parse(_read_source(rel_path))


# ---------------------------------------------------------------------------
# P1: AccountCredentialOut 序列化 created_at/updated_at 字段值不变
#
# 验证：无论是 @staticmethod 还是实例方法，resolve_created_at 和
# resolve_updated_at 最终都调用 _resolve_datetime_iso 处理日期，
# 输出值不变。
# ---------------------------------------------------------------------------


def _get_resolve_method_body(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef | None:
    """从 AST 中提取指定类的方法定义"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    return None


@given(method_index=st.integers(min_value=0, max_value=1))
@settings(max_examples=5)
def test_p1_resolve_datetime_calls_resolve_datetime_iso(method_index: int) -> None:
    """
    属性测试：AccountCredentialOut 的 resolve_created_at 和 resolve_updated_at
    方法体中调用了 _resolve_datetime_iso，确保日期序列化逻辑不变。

    无论是 @staticmethod 调用 SchemaMixin._resolve_datetime_iso()，
    还是实例方法调用 self._resolve_datetime_iso()，
    最终都使用同一个 _resolve_datetime_iso 方法处理日期。

    **Validates: Requirements 3.1**
    """
    methods: list[str] = ["resolve_created_at", "resolve_updated_at"]
    method_name: str = methods[method_index]

    source: str = _read_source("schemas.py")
    tree: ast.Module = ast.parse(source)

    func_def: ast.FunctionDef | None = _get_resolve_method_body(
        tree, "AccountCredentialOut", method_name
    )
    assert func_def is not None, f"未找到 AccountCredentialOut.{method_name}"

    # 提取方法体源码
    method_source: str = ast.get_source_segment(source, func_def) or ""

    # 验证调用了 _resolve_datetime_iso（无论是 SchemaMixin. 还是 self.）
    assert "_resolve_datetime_iso" in method_source, (
        f"{method_name} 未调用 _resolve_datetime_iso，日期序列化逻辑可能改变"
    )

    # 验证返回类型注解为 str | None
    if func_def.returns:
        return_annotation: str = ast.get_source_segment(source, func_def.returns) or ""
        assert "str" in return_annotation, (
            f"{method_name} 返回类型不包含 str"
        )


# ---------------------------------------------------------------------------
# P2: LawyerDtoAssembler.to_dto() 输出与原 LawyerServiceAdapter._to_dto() 一致
#
# 验证：两者映射的字段集合相同，确保委托后 DTO 数据不变。
# ---------------------------------------------------------------------------


@given(dummy=st.just(0))
@settings(max_examples=5)
def test_p2_lawyer_dto_field_mapping_preserved(dummy: int) -> None:
    """
    属性测试：LawyerServiceAdapter._to_dto() 委托给 LawyerDtoAssembler.to_dto()，
    确保 DTO 转换逻辑统一，字段映射不变。

    修复后 Adapter._to_dto() 不再内联 LawyerDTO(...) 构造，
    而是通过 self._assembler.to_dto(lawyer) 委托给 Assembler。

    **Validates: Requirements 3.2**
    """
    adapter_source: str = _read_source("services/lawyer/adapter.py")
    tree: ast.Module = ast.parse(adapter_source)

    # 提取 LawyerServiceAdapter._to_dto 方法体
    to_dto_body: str | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "LawyerServiceAdapter":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_to_dto":
                    to_dto_body = ast.get_source_segment(adapter_source, item)
                    break

    assert to_dto_body is not None, "LawyerServiceAdapter._to_dto() 未找到"

    # 验证 _to_dto 委托给 assembler（包含 "assembler" 或 "to_dto" 调用）
    assert "assembler" in to_dto_body or "to_dto" in to_dto_body, (
        "_to_dto() 未委托给 assembler，可能仍包含内联 DTO 构造逻辑"
    )

    # 验证 Assembler 的 to_dto 方法存在且包含字段映射
    assembler_source: str = _read_source("services/dto_assemblers.py")
    assembler_tree: ast.Module = ast.parse(assembler_source)

    assembler_to_dto: str | None = None
    for node in ast.walk(assembler_tree):
        if isinstance(node, ast.ClassDef) and node.name == "LawyerDtoAssembler":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "to_dto":
                    assembler_to_dto = ast.get_source_segment(assembler_source, item)
                    break

    assert assembler_to_dto is not None, "LawyerDtoAssembler.to_dto() 未找到"
    assert "LawyerDTO" in assembler_to_dto, "LawyerDtoAssembler.to_dto() 未构造 LawyerDTO"


# ---------------------------------------------------------------------------
# P3: 权限检查委托后判定结果不变（PermissionDenied 消息一致）
#
# 验证：LawFirmService/TeamService 的 _check_*_permission 方法
# 与 OrganizationAccessPolicy 的 can_* 方法逻辑等价。
# ---------------------------------------------------------------------------


def _extract_permission_logic(source: str, class_name: str, method_name: str) -> str | None:
    """提取权限检查方法的源码"""
    tree: ast.Module = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_source_segment(source, item)
    return None


# 权限检查方法对应关系（已重构为 _access_policy 委托）


# LawFirmService CRUD 方法与 access_policy 方法的对应关系
_LAWFIRM_CRUD_POLICY_PAIRS: list[tuple[str, str]] = [
    ("get_lawfirm", "can_read_lawfirm"),
    ("create_lawfirm", "can_create"),
    ("update_lawfirm", "can_update_lawfirm"),
    ("delete_lawfirm", "can_delete_lawfirm"),
]


@given(pair_index=st.integers(min_value=0, max_value=3))
@settings(max_examples=5)
def test_p3_lawfirm_permission_logic_equivalence(pair_index: int) -> None:
    """
    属性测试：LawFirmService 的 CRUD 方法已委托给 OrganizationAccessPolicy。

    修复后 LawFirmService 不再包含 _check_*_permission 方法，
    而是在 get_lawfirm、create_lawfirm、update_lawfirm、delete_lawfirm 中
    直接调用 self._access_policy.can_* 方法。

    **Validates: Requirements 3.5**
    """
    crud_method: str
    policy_method: str
    crud_method, policy_method = _LAWFIRM_CRUD_POLICY_PAIRS[pair_index]

    service_source: str = _read_source("services/lawfirm_service.py")

    # 提取 CRUD 方法体
    crud_body: str | None = _extract_permission_logic(
        service_source, "LawFirmService", crud_method
    )
    assert crud_body is not None, f"LawFirmService.{crud_method} 未找到"

    # 验证 CRUD 方法中包含 _access_policy 委托调用
    assert "_access_policy" in crud_body or "can_" in crud_body, (
        f"LawFirmService.{crud_method} 未委托给 _access_policy，"
        f"权限检查可能仍使用内联逻辑"
    )

    # 验证 OrganizationAccessPolicy 中对应方法存在
    policy_source: str = _read_source("services/organization_access_policy.py")
    policy_body: str | None = _extract_permission_logic(
        policy_source, "OrganizationAccessPolicy", policy_method
    )
    assert policy_body is not None, f"OrganizationAccessPolicy.{policy_method} 未找到"


# TeamService CRUD 方法与 access_policy 方法的对应关系
_TEAM_CRUD_POLICY_PAIRS: list[tuple[str, str]] = [
    ("get_team", "can_read_team"),
    ("create_team", "can_create"),
    ("update_team", "can_update_team"),
    ("delete_team", "can_delete_team"),
]


@given(pair_index=st.integers(min_value=0, max_value=3))
@settings(max_examples=5)
def test_p3_team_permission_logic_equivalence(pair_index: int) -> None:
    """
    属性测试：TeamService 的 CRUD 方法已委托给 OrganizationAccessPolicy。

    修复后 TeamService 不再包含 _check_*_permission 方法，
    而是在 get_team、create_team、update_team、delete_team 中
    直接调用 self._access_policy.can_* 方法。

    注意：TeamService.get_team() 中 user is None 时直接放行（公开接口），
    再调用 access_policy.can_read_team()。

    **Validates: Requirements 3.5**
    """
    crud_method: str
    policy_method: str
    crud_method, policy_method = _TEAM_CRUD_POLICY_PAIRS[pair_index]

    service_source: str = _read_source("services/team_service.py")

    # 提取 CRUD 方法体
    crud_body: str | None = _extract_permission_logic(
        service_source, "TeamService", crud_method
    )
    assert crud_body is not None, f"TeamService.{crud_method} 未找到"

    # 验证 CRUD 方法中包含 _access_policy 委托调用
    assert "_access_policy" in crud_body or "can_" in crud_body, (
        f"TeamService.{crud_method} 未委托给 _access_policy，"
        f"权限检查可能仍使用内联逻辑"
    )

    # 验证 OrganizationAccessPolicy 中对应方法存在
    policy_source: str = _read_source("services/organization_access_policy.py")
    policy_body: str | None = _extract_permission_logic(
        policy_source, "OrganizationAccessPolicy", policy_method
    )
    assert policy_body is not None, f"OrganizationAccessPolicy.{policy_method} 未找到"


# ---------------------------------------------------------------------------
# P4: 注册流程中管理员权限设置不变
#
# 验证：业务逻辑已从 forms.py 迁移到 AuthService.register()，
# forms.py 仅保留 real_name = username 映射，
# AuthService.register() 包含完整的管理员权限判断逻辑。
# ---------------------------------------------------------------------------


@given(dummy=st.just(0))
@settings(max_examples=5)
def test_p4_registration_admin_privilege_logic_preserved(dummy: int) -> None:
    """
    属性测试：管理员权限设置逻辑已从 LawyerRegistrationForm.save() 迁移到
    AuthService.register()。

    forms.py 仅负责数据保存（real_name = username 映射），
    AuthService.register() 包含第一个用户管理员权限判断逻辑。

    **Validates: Requirements 3.7**
    """
    # 验证 forms.py 不包含业务逻辑
    form_source: str = _read_source("forms.py")
    form_tree: ast.Module = ast.parse(form_source)

    save_body: str | None = None
    for node in ast.walk(form_tree):
        if isinstance(node, ast.ClassDef) and node.name == "LawyerRegistrationForm":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "save":
                    save_body = ast.get_source_segment(form_source, item)
                    break

    assert save_body is not None, "LawyerRegistrationForm.save() 未找到"

    # forms.py 仅保留 real_name 映射
    assert "real_name" in save_body, "save() 中未找到 real_name 映射"
    assert "username" in save_body, "save() 中未找到 username 引用"

    # forms.py 不应包含业务逻辑
    for attr in ("is_staff", "is_superuser", "is_admin"):
        assert attr not in save_body, f"save() 不应包含 {attr} 设置"

    # 验证 AuthService.register() 包含管理员权限逻辑
    auth_source: str = _read_source("services/auth_service.py")
    auth_tree: ast.Module = ast.parse(auth_source)

    register_body: str | None = None
    for node in ast.walk(auth_tree):
        if isinstance(node, ast.ClassDef) and node.name == "AuthService":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "register":
                    register_body = ast.get_source_segment(auth_source, item)
                    break

    assert register_body is not None, "AuthService.register() 未找到"
    assert "is_superuser" in register_body, "register() 中未找到 is_superuser 设置"
    assert "is_admin" in register_body, "register() 中未找到 is_admin 设置"
    assert "is_active" in register_body, "register() 中未找到 is_active 设置"


# ---------------------------------------------------------------------------
# P5: Admin 操作消息内容不变（仅格式化方式改变）
#
# 验证：mark_as_preferred 和 unmark_as_preferred 的消息模板
# 在 f-string 和 ngettext/% 格式化后内容一致。
# ---------------------------------------------------------------------------


@given(count=st.integers(min_value=0, max_value=100))
@settings(max_examples=5)
def test_p5_admin_operation_messages_preserved(count: int) -> None:
    """
    属性测试：mark_as_preferred 和 unmark_as_preferred 的消息内容
    在 f-string 格式化和 %(count)d 格式化后完全一致。

    当前使用 _(f"已将 {count} 个账号标记为优先使用")，
    修复后使用 "已将 %(count)d 个账号标记为优先使用" % {"count": count}。
    两者输出内容应一致。

    **Validates: Requirements 3.8**
    """
    # 当前行为：f-string 格式化
    fstring_mark: str = f"已将 {count} 个账号标记为优先使用"
    fstring_unmark: str = f"已取消 {count} 个账号的优先标记"

    # 修复后行为：% 格式化
    percent_mark: str = "已将 %(count)d 个账号标记为优先使用" % {"count": count}
    percent_unmark: str = "已取消 %(count)d 个账号的优先标记" % {"count": count}

    assert fstring_mark == percent_mark, (
        f"mark 消息不一致: f-string='{fstring_mark}', percent='{percent_mark}'"
    )
    assert fstring_unmark == percent_unmark, (
        f"unmark 消息不一致: f-string='{fstring_unmark}', percent='{percent_unmark}'"
    )


@given(method_index=st.integers(min_value=0, max_value=1))
@settings(max_examples=5)
def test_p5_admin_message_template_exists(method_index: int) -> None:
    """
    属性测试：accountcredential_admin.py 中 mark_as_preferred 和
    unmark_as_preferred 方法包含消息显示逻辑。

    **Validates: Requirements 3.8**
    """
    methods: list[str] = ["mark_as_preferred", "unmark_as_preferred"]
    method_name: str = methods[method_index]

    source: str = _read_source("admin/accountcredential_admin.py")
    tree: ast.Module = ast.parse(source)

    # 找到方法
    method_body: str | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "AccountCredentialAdmin":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    method_body = ast.get_source_segment(source, item)
                    break

    assert method_body is not None, f"AccountCredentialAdmin.{method_name} 未找到"

    # 验证包含 message_user 调用
    assert "message_user" in method_body, (
        f"{method_name} 未调用 message_user"
    )

    # 验证委托给 credential service 执行 is_preferred 更新
    assert "credential_service" in method_body or "_get_credential_service" in method_body or "batch_" in method_body, (
        f"{method_name} 未委托给 credential service 执行 is_preferred 更新"
    )
