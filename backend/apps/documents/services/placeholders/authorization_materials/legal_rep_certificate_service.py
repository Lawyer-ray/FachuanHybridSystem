"""Business logic services."""

from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry


@PlaceholderRegistry.register
class LegalRepCertificatePlaceholderService(BasePlaceholderService):
    name: str = "legal_rep_certificate_placeholder_service"
    display_name: str = "授权委托材料-法定代表人身份证明书"
    description: str = "生成法定代表人身份证明书所需占位符"
    category: str = "authorization_material"
    placeholder_keys: ClassVar = ["法人名称", "法定代表人姓名"]
    placeholder_metadata: ClassVar = {
        "法人名称": {
            "display_name": "法人名称",
            "description": "我方当事人(法人)的名称",
            "example_value": "XX有限公司",
        },
        "法定代表人姓名": {
            "display_name": "法定代表人姓名",
            "description": "我方当事人(法人)的法定代表人姓名",
            "example_value": "张三",
        },
    }

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        client = context_data.get("client")
        if not client:
            return {
                "法人名称": "",
                "法定代表人姓名": "",
            }

        return {
            "法人名称": getattr(client, "name", "") or "",
            "法定代表人姓名": getattr(client, "legal_representative", "") or "",
        }
