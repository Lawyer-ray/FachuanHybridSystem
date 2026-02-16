from typing import Any, Dict

from apps.documents.services.placeholders import BasePlaceholderService, PlaceholderRegistry


class _TestPlaceholderService(BasePlaceholderService):
    name = "test_service"
    display_name = "测试服务"
    description = "用于测试"
    category = "test"
    placeholder_keys = ["case_name"]
    placeholder_metadata = {"case_name": {"display_name": "案件名称", "description": "案件名称", "example_value": "示例"}}

    def generate(self, context_data: Dict[str, Any]) -> Dict[str, Any]:
        return {"case_name": "X"}


def test_list_registered_services_includes_placeholder_metadata():
    registry = PlaceholderRegistry()
    registry.clear()
    PlaceholderRegistry.register(_TestPlaceholderService)

    info = registry.list_registered_services()
    assert "test_service" in info
    assert info["test_service"]["placeholder_metadata"]["case_name"]["display_name"] == "案件名称"

    registry.clear()
