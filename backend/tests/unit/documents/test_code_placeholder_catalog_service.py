from apps.documents.services.code_placeholder_catalog_service import CodePlaceholderCatalogService
from apps.documents.services.code_placeholder_registry import CodePlaceholderRegistry, expose_placeholders
from apps.documents.services.evidence_list_placeholder_service import EvidenceListPlaceholderService


def test_catalog_includes_litigation_and_evidence_keys():
    catalog = CodePlaceholderCatalogService()
    keys = set(catalog.list_keys())

    assert "案由" in keys
    assert "起诉状当事人信息" in keys
    assert "答辩状当事人信息" in keys
    assert "证据清单名称" in keys


def test_evidence_list_service_exposes_placeholder_keys():
    service = EvidenceListPlaceholderService()
    assert service.get_placeholder_keys() == [
        "证据清单名称",
        "当事人信息_简要",
        "证据清单",
        "证据清单签名盖章信息",
    ]


def test_expose_placeholders_registers_to_catalog():
    registry = CodePlaceholderRegistry()
    registry.clear()

    @expose_placeholders(
        keys=["自定义占位符A", "自定义占位符B"],
        source="测试来源",
        category="test",
        metadata={"自定义占位符A": {"display_name": "A", "description": "desc", "example_value": "ex"}},
    )
    class _Dummy:
        pass

    keys = set(CodePlaceholderCatalogService().list_keys())
    assert "自定义占位符A" in keys
    assert "自定义占位符B" in keys
