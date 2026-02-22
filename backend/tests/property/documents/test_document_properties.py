"""
Documents 模块属性测试

**Feature: backend-perfect-score**

覆盖以下属性：
- Property D1: 文件夹路径计算一致性
- Property D2: 文件夹路径计算幂等性

**Validates: Requirements 8.2**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.documents.services.contract_template_binding_service import DocumentTemplateBindingService


# ── 策略 ──────────────────────────────────────────────────────────────────────

# 节点 ID 策略
node_id_strategy = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
)

# 节点名称策略
node_name_strategy = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
)


def _make_folder_template(structure: dict) -> object:
    """创建带 structure 属性的 mock 对象"""

    class FakeFolderTemplate:
        pass

    ft = FakeFolderTemplate()
    ft.structure = structure  # type: ignore[attr-defined]
    return ft


# ── Property D1: 文件夹路径计算一致性 ─────────────────────────────────────────


@given(
    node_id=node_id_strategy,
    node_name=node_name_strategy,
)
@settings(max_examples=100)
def test_property_folder_path_found_when_node_exists(node_id: str, node_name: str) -> None:
    """
    **Feature: backend-perfect-score, Property D1: 文件夹路径计算一致性**

    当节点 ID 存在于结构中时，calculate_folder_path 必须返回非空路径，
    且路径中包含该节点的名称。

    **Validates: Requirements 8.2**
    """
    service = DocumentTemplateBindingService()

    structure = {
        "children": [
            {"id": node_id, "name": node_name, "children": []},
        ]
    }
    ft = _make_folder_template(structure)

    result = service.calculate_folder_path(ft, node_id)  # type: ignore[arg-type]

    assert result != "", f"节点 '{node_id}' 存在但路径为空"
    assert node_name in result, f"路径 '{result}' 不包含节点名称 '{node_name}'"


@given(
    node_id=node_id_strategy,
    missing_id=node_id_strategy,
    node_name=node_name_strategy,
)
@settings(max_examples=100)
def test_property_folder_path_empty_when_node_missing(node_id: str, missing_id: str, node_name: str) -> None:
    """
    **Feature: backend-perfect-score, Property D1: 文件夹路径计算一致性**

    当查找的节点 ID 不存在于结构中时，calculate_folder_path 必须返回空字符串。

    **Validates: Requirements 8.2**
    """
    from hypothesis import assume

    assume(node_id != missing_id)

    service = DocumentTemplateBindingService()

    structure = {
        "children": [
            {"id": node_id, "name": node_name, "children": []},
        ]
    }
    ft = _make_folder_template(structure)

    result = service.calculate_folder_path(ft, missing_id)  # type: ignore[arg-type]

    assert result == "", f"节点 '{missing_id}' 不存在但路径非空: '{result}'"


# ── Property D2: 文件夹路径计算幂等性 ─────────────────────────────────────────


@given(
    node_id=node_id_strategy,
    parent_name=node_name_strategy,
    child_name=node_name_strategy,
)
@settings(max_examples=100)
def test_property_nested_folder_path_contains_all_ancestors(node_id: str, parent_name: str, child_name: str) -> None:
    """
    **Feature: backend-perfect-score, Property D2: 文件夹路径计算幂等性**

    对于嵌套节点，calculate_folder_path 返回的路径应包含所有祖先节点名称，
    以 '/' 分隔，且顺序从根到叶。

    **Validates: Requirements 8.2**
    """
    service = DocumentTemplateBindingService()

    structure = {
        "children": [
            {
                "id": "parent",
                "name": parent_name,
                "children": [
                    {"id": node_id, "name": child_name, "children": []},
                ],
            }
        ]
    }
    ft = _make_folder_template(structure)

    result = service.calculate_folder_path(ft, node_id)  # type: ignore[arg-type]

    assert result != "", f"嵌套节点 '{node_id}' 路径为空"
    parts = result.split("/")
    assert len(parts) == 2, f"嵌套路径应有 2 段，实际: {parts}"
    assert parts[0] == parent_name, f"路径第一段应为父节点名 '{parent_name}'，实际: '{parts[0]}'"
    assert parts[1] == child_name, f"路径第二段应为子节点名 '{child_name}'，实际: '{parts[1]}'"
