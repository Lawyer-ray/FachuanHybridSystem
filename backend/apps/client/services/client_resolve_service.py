"""当事人 get_or_create 解析服务（用于 JSON 导入）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext_lazy as _

from apps.client.models import Client
from apps.client.services.importer.validator import ClientJsonImportValidator
from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    pass

logger = logging.getLogger("apps.client")

_CLIENT_FIELDS: tuple[str, ...] = (
    "name",
    "phone",
    "address",
    "client_type",
    "id_number",
    "legal_representative",
    "legal_representative_id_number",
    "is_our_client",
)


class ClientResolveService:
    """按 id_number get_or_create Client，维护会话内缓存避免重复创建。"""

    def __init__(self) -> None:
        self._cache: dict[str, Client] = {}
        self._validator = ClientJsonImportValidator()

    def resolve(self, data: dict[str, Any]) -> Client:
        id_number: str | None = data.get("id_number")

        # 有 id_number 时先查缓存再查库
        if id_number:
            if id_number in self._cache:
                return self._cache[id_number]
            existing = Client.objects.filter(id_number=id_number).first()
            if existing:
                self._cache[id_number] = existing
                logger.info("复用已有当事人", extra={"client_id": existing.pk, "id_number": id_number})
                return existing

        # 校验
        try:
            self._validator.validate(data)
        except ValidationException as exc:
            raise ValidationException(
                message=_("当事人数据验证失败: %(name)s") % {"name": data.get("name", "")},
                code="INVALID_CLIENT_DATA",
                errors=exc.errors,
            ) from exc

        client_data = {f: data[f] for f in _CLIENT_FIELDS if f in data}
        client_data.setdefault("is_our_client", False)
        client = Client.objects.create(**client_data)

        if id_number:
            self._cache[id_number] = client

        logger.info("创建新当事人", extra={"client_id": client.pk, "name": client.name})
        return client
