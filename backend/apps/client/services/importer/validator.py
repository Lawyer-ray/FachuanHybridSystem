"""当事人 JSON 导入校验器。"""

from django.utils.translation import gettext_lazy as _
from typing import Any

from apps.client.models import Client
from apps.core.exceptions import ValidationException


class ClientJsonImportValidator:
    def validate(self, json_data: dict[str, Any]) -> None:
        errors: dict[str, Any] = {}

        if not json_data.get("name"):
            errors["name"] = _("客户名称不能为空")

        client_type = json_data.get("client_type")
        valid_types = [Client.NATURAL, Client.LEGAL, Client.NON_LEGAL_ORG]
        if not client_type or client_type not in valid_types:
            errors["client_type"] = _("客户类型必须是: %(types)s") % {"types": ", ".join(valid_types)}

        if client_type == Client.LEGAL and not json_data.get("legal_representative"):
            errors["legal_representative"] = _("法人客户必须填写法定代表人")

        if "identity_docs" in json_data:
            self._validate_identity_docs_data(json_data["identity_docs"], errors)

        if errors:
            raise ValidationException(message=_("JSON 数据验证失败"), code="INVALID_JSON", errors=errors)

    def _validate_identity_docs_data(self, docs_data: list[dict[str, Any]], errors: dict[str, Any]) -> None:
        if not isinstance(docs_data, list):
            errors["identity_docs"] = _("证件文档数据必须是列表")
            return

        doc_errors = []
        for i, doc in enumerate(docs_data):
            if not isinstance(doc, dict):
                doc_errors.append(str(_("第 %(n)s 个证件文档数据格式错误") % {"n": i + 1}))
                continue

            if not doc.get("doc_type"):
                doc_errors.append(str(_("第 %(n)s 个证件文档缺少 doc_type") % {"n": i + 1}))

            if not doc.get("file_path"):
                doc_errors.append(str(_("第 %(n)s 个证件文档缺少 file_path") % {"n": i + 1}))

        if doc_errors:
            errors["identity_docs"] = doc_errors
