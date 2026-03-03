# Feature: client-quality-uplift, Property 1: Service 层无运行时 Model 导入
"""
client-quality-uplift 属性测试。

使用 hypothesis 对设计文档中定义的正确性属性进行验证。
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

logger = logging.getLogger(__name__)

# backend/ 根目录
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent

# ---------------------------------------------------------------------------
# 公共 AST 工具
# ---------------------------------------------------------------------------


def _parse_file(rel_path: str) -> ast.Module:
    """解析 Python 文件为 AST。"""
    full_path: Path = BACKEND_DIR / rel_path
    source: str = full_path.read_text(encoding="utf-8")
    return ast.parse(source, filename=rel_path)


def _has_runtime_model_import(tree: ast.Module) -> list[dict[str, Any]]:
    """
    检测模块级 ``from apps.client.models import ...`` 是否在 TYPE_CHECKING 块之外。

    返回违规导入列表，每项包含 line（行号）和 names（导入名称）。
    """
    violations: list[dict[str, Any]] = []

    for node in ast.iter_child_nodes(tree):
        # 跳过 TYPE_CHECKING 块内的导入
        if isinstance(node, ast.If):
            test = node.test
            is_type_checking: bool = False
            if (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            ):
                is_type_checking = True
            if is_type_checking:
                continue

        # 检测模块级 from apps.client.models import ...
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("apps.client.models"):
                names: list[str] = [alias.name for alias in (node.names or [])]
                violations.append(
                    {
                        "line": node.lineno,
                        "names": names,
                    }
                )

    return violations


# ---------------------------------------------------------------------------
# Property 1: Service 层无运行时 Model 导入
# ---------------------------------------------------------------------------

SERVICE_FILES: list[str] = [
    "apps/client/services/client_identity_doc_service.py",
    "apps/client/services/client_admin_file_mixin.py",
    "apps/client/services/client_dto_assembler.py",
]


@pytest.mark.property_test
@settings(max_examples=100)
@given(file_rel_path=st.sampled_from(SERVICE_FILES))
def test_property1_service_no_runtime_model_import(file_rel_path: str) -> None:
    """
    Property 1: Service 层无运行时 Model 导入

    *For any* Service 层 Python 文件，其模块级 ``from apps.client.models import ...``
    语句必须位于 ``TYPE_CHECKING`` 守卫块内，不得存在守卫块外的运行时 Model 导入。

    **Validates: Requirements 1.1, 1.2, 1.3**
    """
    tree: ast.Module = _parse_file(file_rel_path)
    violations: list[dict[str, Any]] = _has_runtime_model_import(tree)

    assert not violations, f"架构违规: {file_rel_path} 存在运行时 Model 导入 (不在 TYPE_CHECKING 块内):\n" + "\n".join(
        f"  第 {v['line']} 行: from apps.client.models import {', '.join(v['names'])}" for v in violations
    )


# ---------------------------------------------------------------------------
# Property 2: Admin 层无直接 Service 实例化
# ---------------------------------------------------------------------------

ADMIN_MIXIN_FILE: str = "apps/client/services/client_admin_file_mixin.py"


def _find_getattr_fallbacks(tree: ast.Module) -> list[dict[str, Any]]:
    """
    检测 ``getattr(self, "identity_doc_service", ...)`` 调用。

    返回违规列表，每项包含 line（行号）和 code（源码片段）。
    """
    violations: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "getattr"):
            continue
        # getattr 至少 2 个参数；检查第二个参数是否为 "identity_doc_service"
        if len(node.args) >= 2:
            second_arg = node.args[1]
            if isinstance(second_arg, ast.Constant) and second_arg.value == "identity_doc_service":
                violations.append(
                    {
                        "line": node.lineno,
                        "code": ast.dump(node),
                    }
                )
    return violations


def _find_direct_service_instantiation(tree: ast.Module) -> list[dict[str, Any]]:
    """
    检测直接 ``ClientIdentityDocService()`` 实例化调用。

    返回违规列表，每项包含 line（行号）和 code（源码片段）。
    """
    violations: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_direct: bool = False
        if (isinstance(func, ast.Name) and func.id == "ClientIdentityDocService") or (
            isinstance(func, ast.Attribute) and func.attr == "ClientIdentityDocService"
        ):
            is_direct = True
        if is_direct:
            violations.append(
                {
                    "line": node.lineno,
                    "code": ast.dump(node),
                }
            )
    return violations


# Feature: client-quality-uplift, Property 2: Admin 层无直接 Service 实例化
@pytest.mark.property_test
def test_property2_admin_no_getattr_fallback() -> None:
    """
    Property 2a: Admin 层无 getattr 回退。

    ``client_admin_file_mixin.py`` 中不得存在
    ``getattr(self, "identity_doc_service", ...)`` 调用。

    **Validates: Requirements 2.1, 11.1, 11.2**
    """
    tree: ast.Module = _parse_file(ADMIN_MIXIN_FILE)
    violations: list[dict[str, Any]] = _find_getattr_fallbacks(tree)

    assert not violations, f"架构违规: {ADMIN_MIXIN_FILE} 存在 getattr 回退:\n" + "\n".join(
        f"  第 {v['line']} 行: {v['code']}" for v in violations
    )


@pytest.mark.property_test
def test_property2_admin_no_direct_service_instantiation() -> None:
    """
    Property 2b: Admin 层无直接 Service 实例化。

    ``client_admin_file_mixin.py`` 中不得存在直接
    ``ClientIdentityDocService()`` 实例化调用。
    所有服务访问必须通过 ``self.identity_doc_service``。

    **Validates: Requirements 2.1, 11.1, 11.2**
    """
    tree: ast.Module = _parse_file(ADMIN_MIXIN_FILE)
    violations: list[dict[str, Any]] = _find_direct_service_instantiation(tree)

    assert not violations, f"架构违规: {ADMIN_MIXIN_FILE} 存在直接 Service 实例化:\n" + "\n".join(
        f"  第 {v['line']} 行: {v['code']}" for v in violations
    )


# ---------------------------------------------------------------------------
# Property 3: Service 层无异常吞没
# ---------------------------------------------------------------------------


def _find_try_except_in_method(tree: ast.Module, class_name: str, method_name: str) -> list[dict[str, Any]]:
    """
    在指定类的指定方法体中查找 ``try/except`` 块。

    返回违规列表，每项包含 line（行号）。
    """
    violations: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name != method_name:
                continue
            # 遍历方法体，查找 ast.Try 节点
            for child in ast.walk(item):
                if isinstance(child, ast.Try):
                    violations.append({"line": child.lineno})
    return violations


# Feature: client-quality-uplift, Property 3: Service 层无异常吞没
@pytest.mark.property_test
def test_property3_no_exception_swallowing() -> None:
    """
    Property 3: Service 层无异常吞没。

    ``ClientAdminFileMixin._update_identity_doc`` 方法体中不得包含
    ``try/except`` 块。``DoesNotExist`` 异常应正常传播给调用方。

    **Validates: Requirements 3.1, 3.2**
    """
    tree: ast.Module = _parse_file(ADMIN_MIXIN_FILE)
    violations: list[dict[str, Any]] = _find_try_except_in_method(tree, "ClientAdminFileMixin", "_update_identity_doc")

    assert not violations, (
        f"架构违规: {ADMIN_MIXIN_FILE} 的 _update_identity_doc 方法存在 try/except 块:\n"
        + "\n".join(f"  第 {v['line']} 行: try/except" for v in violations)
    )


# ---------------------------------------------------------------------------
# Property 4: resolve_media_url 路径解析正确性
# ---------------------------------------------------------------------------

# Feature: client-quality-uplift, Property 4: resolve_media_url 路径解析正确性


@pytest.mark.property_test
@settings(max_examples=100)
@given(file_path=st.text(min_size=1))
def test_property4_resolve_media_url_correctness(file_path: str) -> None:
    """
    Property 4: resolve_media_url 路径解析正确性。

    *For any* 非空文件路径字符串 ``p``，``resolve_media_url(p)`` 返回的 URL
    必须以 ``settings.MEDIA_URL`` 开头，且不包含反斜杠。
    对于空字符串，必须返回 ``None``。

    **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
    """
    from django.conf import settings as django_settings

    from apps.client.utils.media import resolve_media_url

    result: str | None = resolve_media_url(file_path)

    if result is not None:
        assert result.startswith(django_settings.MEDIA_URL), (
            f"resolve_media_url({file_path!r}) = {result!r} 不以 MEDIA_URL ({django_settings.MEDIA_URL!r}) 开头"
        )
        assert "\\" not in result, f"resolve_media_url({file_path!r}) = {result!r} 包含反斜杠"


@pytest.mark.property_test
def test_property4_resolve_media_url_empty_returns_none() -> None:
    """
    Property 4 补充: 空字符串必须返回 None。

    **Validates: Requirements 4.3**
    """
    from apps.client.utils.media import resolve_media_url

    result: str | None = resolve_media_url("")
    assert result is None, f"resolve_media_url('') 应返回 None，实际返回 {result!r}"


# ---------------------------------------------------------------------------
# Property 5: Model media_url property 等价于 resolve_media_url
# ---------------------------------------------------------------------------

# Feature: client-quality-uplift, Property 5: Model media_url property 等价于 resolve_media_url


@pytest.mark.property_test
@settings(max_examples=100)
@given(file_path=st.text())
def test_property5_identity_doc_media_url_equivalence(file_path: str) -> None:
    """
    Property 5a: ClientIdentityDoc.media_url property 等价于 resolve_media_url。

    *For any* 具有 ``file_path`` 属性的 ``ClientIdentityDoc`` 实例，
    其 ``media_url`` property 的返回值必须等于
    ``resolve_media_url(instance.file_path)`` 的返回值。

    **Validates: Requirements 4.5, 5.1**
    """
    from unittest.mock import MagicMock

    from apps.client.models.identity_doc import ClientIdentityDoc
    from apps.client.utils.media import resolve_media_url

    doc: MagicMock = MagicMock(spec=ClientIdentityDoc)
    doc.file_path = file_path

    # 通过 property descriptor 的 fget 获取真实 property 逻辑
    prop_fget = ClientIdentityDoc.media_url.fget
    assert prop_fget is not None, "ClientIdentityDoc.media_url 应为 @property"
    prop_result: str | None = prop_fget(doc)
    expected: str | None = resolve_media_url(file_path)

    assert prop_result == expected, (
        f"ClientIdentityDoc.media_url 不等价于 resolve_media_url:\n"
        f"  file_path={file_path!r}\n"
        f"  property={prop_result!r}\n"
        f"  resolve_media_url={expected!r}"
    )


@pytest.mark.property_test
@settings(max_examples=100)
@given(file_path=st.text())
def test_property5_attachment_media_url_equivalence(file_path: str) -> None:
    """
    Property 5b: PropertyClueAttachment.media_url property 等价于 resolve_media_url。

    *For any* 具有 ``file_path`` 属性的 ``PropertyClueAttachment`` 实例，
    其 ``media_url`` property 的返回值必须等于
    ``resolve_media_url(instance.file_path)`` 的返回值。

    **Validates: Requirements 4.6, 5.2**
    """
    from unittest.mock import MagicMock

    from apps.client.models.property_clue import PropertyClueAttachment
    from apps.client.utils.media import resolve_media_url

    attachment: MagicMock = MagicMock(spec=PropertyClueAttachment)
    attachment.file_path = file_path

    # 通过 property descriptor 的 fget 获取真实 property 逻辑
    prop_fget = PropertyClueAttachment.media_url.fget
    assert prop_fget is not None, "PropertyClueAttachment.media_url 应为 @property"
    prop_result: str | None = prop_fget(attachment)
    expected: str | None = resolve_media_url(file_path)

    assert prop_result == expected, (
        f"PropertyClueAttachment.media_url 不等价于 resolve_media_url:\n"
        f"  file_path={file_path!r}\n"
        f"  property={prop_result!r}\n"
        f"  resolve_media_url={expected!r}"
    )


# ---------------------------------------------------------------------------
# Property 6: 调用点无 media_url() 方法调用
# ---------------------------------------------------------------------------

CALL_SITE_FILES: list[str] = [
    "apps/client/schemas.py",
    "apps/client/api/clientidentitydoc_api.py",
    "apps/client/services/client_dto_assembler.py",
]


def _find_media_url_method_calls(tree: ast.Module) -> list[dict[str, Any]]:
    """
    检测 ``obj.media_url()`` 形式的方法调用。

    遍历 AST，查找 ``ast.Call`` 节点，其 ``func`` 为
    ``ast.Attribute(attr="media_url")``，即 ``something.media_url()``。

    返回违规列表，每项包含 line（行号）。
    """
    violations: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "media_url":
            violations.append({"line": node.lineno})
    return violations


# Feature: client-quality-uplift, Property 6: 调用点无 media_url() 方法调用
@pytest.mark.property_test
@settings(max_examples=100)
@given(file_rel_path=st.sampled_from(CALL_SITE_FILES))
def test_property6_no_media_url_method_calls(file_rel_path: str) -> None:
    """
    Property 6: 调用点无 media_url() 方法调用。

    *For any* ``schemas.py``、``clientidentitydoc_api.py``、
    ``client_dto_assembler.py`` 文件中的 AST，不得存在
    ``obj.media_url()`` 形式的函数调用（即 ``media_url`` 后跟 ``()`` 括号）。

    **Validates: Requirements 5.3**
    """
    tree: ast.Module = _parse_file(file_rel_path)
    violations: list[dict[str, Any]] = _find_media_url_method_calls(tree)

    assert not violations, (
        f"架构违规: {file_rel_path} 存在 media_url() 方法调用 "
        f"(应使用属性访问 .media_url 而非方法调用 .media_url()):\n"
        + "\n".join(f"  第 {v['line']} 行: obj.media_url()" for v in violations)
    )


# ---------------------------------------------------------------------------
# Property 7: choices 显示文本为 lazy string
# ---------------------------------------------------------------------------

# Feature: client-quality-uplift, Property 7: choices 显示文本为 lazy string

from django.utils.functional import Promise

from apps.client.models import Client
from apps.client.models.identity_doc import ClientIdentityDoc
from apps.client.models.property_clue import PropertyClue

ALL_CHOICES_DISPLAYS: list[tuple[object, str]] = (
    [(display, "ClientIdentityDoc.DOC_TYPE_CHOICES") for _, display in ClientIdentityDoc.DOC_TYPE_CHOICES]
    + [(display, "PropertyClue.CLUE_TYPE_CHOICES") for _, display in PropertyClue.CLUE_TYPE_CHOICES]
    + [(display, "Client.CLIENT_TYPE_CHOICES") for _, display in Client.CLIENT_TYPE_CHOICES]
)

CONTENT_TEMPLATE_VALUES: list[tuple[object, str]] = [
    (value, "PropertyClue.CONTENT_TEMPLATES")
    for value in PropertyClue.CONTENT_TEMPLATES.values()
    if value  # skip empty strings
]


@pytest.mark.property_test
@settings(max_examples=100)
@given(data=st.sampled_from(ALL_CHOICES_DISPLAYS))
def test_property7_choices_display_is_lazy_string(
    data: tuple[object, str],
) -> None:
    """
    Property 7a: choices 显示文本为 lazy string。

    *For any* ``ClientIdentityDoc.DOC_TYPE_CHOICES``、
    ``PropertyClue.CLUE_TYPE_CHOICES``、``Client.CLIENT_TYPE_CHOICES``
    中的 ``(value, display)`` 元组，``display`` 必须是
    ``django.utils.functional.lazy`` 返回的惰性字符串实例。

    **Validates: Requirements 7.1, 7.2, 7.4**
    """
    display: object = data[0]
    source: str = data[1]

    assert isinstance(display, Promise), (
        f"{source} 中的显示文本 {display!r} 不是 lazy string (类型: {type(display).__name__})，应使用 gettext_lazy 包裹"
    )


@pytest.mark.property_test
@settings(max_examples=100)
@given(data=st.sampled_from(CONTENT_TEMPLATE_VALUES))
def test_property7_content_templates_is_lazy_string(
    data: tuple[object, str],
) -> None:
    """
    Property 7b: CONTENT_TEMPLATES 非空值为 lazy string。

    *For any* ``PropertyClue.CONTENT_TEMPLATES`` 中非空的 value，
    必须是 ``django.utils.functional.lazy`` 返回的惰性字符串实例。

    **Validates: Requirements 7.3**
    """
    value: object = data[0]
    source: str = data[1]

    assert isinstance(value, Promise), (
        f"{source} 中的模板文本 {value!r} 不是 lazy string (类型: {type(value).__name__})，应使用 gettext_lazy 包裹"
    )


# ---------------------------------------------------------------------------
# Property 8: clean() 验证消息为 lazy string
# ---------------------------------------------------------------------------

# Feature: client-quality-uplift, Property 8: clean() 验证消息为 lazy string


@pytest.mark.property_test
def test_property8_identity_doc_clean_messages_are_lazy() -> None:
    """
    Property 8a: ClientIdentityDoc.clean() 验证消息为 lazy string。

    AST 分析 ``ClientIdentityDoc.clean()`` 方法，确认所有传给
    ``ValidationError`` 的字符串值都通过 ``_()`` (gettext_lazy) 包裹。

    **Validates: Requirements 6.1**
    """
    tree = _parse_file("apps/client/models/identity_doc.py")

    # 找到 ClientIdentityDoc 类中的 clean 方法
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ClientIdentityDoc":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "clean":
                    # 找到所有 ValidationError(...) 调用
                    for call_node in ast.walk(item):
                        if (
                            isinstance(call_node, ast.Call)
                            and isinstance(call_node.func, ast.Name)
                            and call_node.func.id == "ValidationError"
                        ):
                            # 检查参数中的 Dict 值是否用 _() 包裹
                            for arg in call_node.args:
                                if isinstance(arg, ast.Dict):
                                    for val in arg.values:
                                        assert isinstance(val, ast.Call) and (
                                            isinstance(val.func, ast.Name) and val.func.id == "_"
                                        ), f"ValidationError 的消息值应使用 _() 包裹，发现: {ast.dump(val)}"
                    return
    pytest.fail("未找到 ClientIdentityDoc.clean() 方法")


@pytest.mark.property_test
def test_property8_client_clean_messages_are_lazy() -> None:
    """
    Property 8b: Client.clean() 验证消息为 lazy string。

    AST 分析 ``Client.clean()`` 方法，确认所有传给
    ``ValidationError`` 的字符串值都通过 ``_()`` (gettext_lazy) 包裹。

    **Validates: Requirements 6.2**
    """
    tree = _parse_file("apps/client/models/client.py")

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Client":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "clean":
                    for call_node in ast.walk(item):
                        if (
                            isinstance(call_node, ast.Call)
                            and isinstance(call_node.func, ast.Name)
                            and call_node.func.id == "ValidationError"
                        ):
                            for arg in call_node.args:
                                if isinstance(arg, ast.Dict):
                                    for val in arg.values:
                                        assert isinstance(val, ast.Call) and (
                                            isinstance(val.func, ast.Name) and val.func.id == "_"
                                        ), f"ValidationError 的消息值应使用 _() 包裹，发现: {ast.dump(val)}"
                    return
    pytest.fail("未找到 Client.clean() 方法")


# ---------------------------------------------------------------------------
# Property 9: mutation service errors 字典值为 lazy string
# ---------------------------------------------------------------------------

# Feature: client-quality-uplift, Property 9: mutation service errors 字典值为 lazy string


@pytest.mark.property_test
def test_property9_validate_create_data_errors_are_lazy() -> None:
    """
    Property 9a: _validate_create_data 的 errors 字典值为 lazy string。

    构造无效数据触发 ``ValidationException``，验证 ``errors`` 字典中
    所有字符串值为 ``Promise`` 实例（惰性字符串）。

    **Validates: Requirements 9.1, 9.2**
    """
    from apps.client.services.client_mutation_service import ClientMutationService
    from apps.core.exceptions import ValidationException

    service: ClientMutationService = ClientMutationService()

    # 空 name 触发验证异常
    with pytest.raises(ValidationException) as exc_info:
        service._validate_create_data({"name": ""})

    errors: dict[str, Any] = exc_info.value.errors
    for field, msg in errors.items():
        assert isinstance(msg, Promise), (
            f"_validate_create_data errors[{field!r}] = {msg!r} "
            f"不是 lazy string (类型: {type(msg).__name__})，"
            f"应使用 gettext_lazy 包裹"
        )

    # 无效 client_type 触发验证异常
    with pytest.raises(ValidationException) as exc_info2:
        service._validate_create_data({"name": "test", "client_type": "invalid"})

    errors2: dict[str, Any] = exc_info2.value.errors
    for field, msg in errors2.items():
        assert isinstance(msg, Promise), (
            f"_validate_create_data errors[{field!r}] = {msg!r} "
            f"不是 lazy string (类型: {type(msg).__name__})，"
            f"应使用 gettext_lazy 包裹"
        )


@pytest.mark.property_test
def test_property9_validate_update_data_errors_are_lazy() -> None:
    """
    Property 9b: _validate_update_data 的 errors 字典值为 lazy string。

    构造无效数据触发 ``ValidationException``，验证 ``errors`` 字典中
    所有字符串值为 ``Promise`` 实例（惰性字符串）。

    **Validates: Requirements 9.1, 9.2**
    """
    from unittest.mock import MagicMock

    from apps.client.services.client_mutation_service import ClientMutationService
    from apps.core.exceptions import ValidationException

    service: ClientMutationService = ClientMutationService()

    mock_client: MagicMock = MagicMock()
    mock_client.client_type = "natural"
    mock_client.legal_representative = ""

    # 空 name 触发验证异常
    with pytest.raises(ValidationException) as exc_info:
        service._validate_update_data(mock_client, {"name": ""})

    errors: dict[str, Any] = exc_info.value.errors
    for field, msg in errors.items():
        assert isinstance(msg, Promise), (
            f"_validate_update_data errors[{field!r}] = {msg!r} "
            f"不是 lazy string (类型: {type(msg).__name__})，"
            f"应使用 gettext_lazy 包裹"
        )


# ---------------------------------------------------------------------------
# Property 10: text_parser 关键字和返回值不做 i18n
# ---------------------------------------------------------------------------

# Feature: client-quality-uplift, Property 10: text_parser 关键字和返回值不做 i18n

from apps.client.services.text_parser import _FIELD_KEYWORDS, parse_client_text


@pytest.mark.property_test
def test_property10_field_keywords_are_plain_str() -> None:
    """
    Property 10a: _FIELD_KEYWORDS 为纯 str。

    *For any* ``_FIELD_KEYWORDS`` 列表中的元素，必须是纯 ``str`` 类型
    而非 ``Promise``（lazy string）。

    **Validates: Requirements 8.1**
    """
    for keyword in _FIELD_KEYWORDS:
        assert isinstance(keyword, str) and not isinstance(keyword, Promise), (
            f"_FIELD_KEYWORDS 中的 {keyword!r} 不是纯 str "
            f"(类型: {type(keyword).__name__})，text_parser 关键字不应做 i18n"
        )


@pytest.mark.property_test
@settings(max_examples=100)
@given(text=st.text())
def test_property10_parse_client_text_client_type_is_plain_str(text: str) -> None:
    """
    Property 10b: parse_client_text 返回的 client_type 为纯 str。

    *For any* 输入文本，``parse_client_text`` 返回结果中的 ``client_type``
    字段值必须是纯 ``str``（如 ``"natural"`` / ``"legal"`` / ``"non_legal_org"``），
    不得为 ``Promise``（lazy string）。

    **Validates: Requirements 8.2**
    """
    result: dict[str, Any] = parse_client_text(text)
    client_type: object = result.get("client_type", "")

    assert isinstance(client_type, str) and not isinstance(client_type, Promise), (
        f"parse_client_text({text!r}) 返回的 client_type={client_type!r} "
        f"不是纯 str (类型: {type(client_type).__name__})，"
        f"text_parser 返回值不应做 i18n"
    )
