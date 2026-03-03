"""律师 get_or_create 解析服务（用于 JSON 导入）。"""

from __future__ import annotations

import logging
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.organization.models import Lawyer

logger = logging.getLogger("apps.organization")

_DEFAULT_PASSWORD = "1234qwer"


class LawyerResolveService:
    """按 phone get_or_create Lawyer，维护会话内缓存避免重复创建。"""

    def __init__(self) -> None:
        self._cache: dict[str, Lawyer] = {}

    def resolve(self, data: dict[str, Any]) -> Lawyer | None:
        phone: str | None = data.get("phone")
        if not phone:
            logger.warning("律师数据缺少 phone，跳过", extra={"data": data})
            return None

        if phone in self._cache:
            return self._cache[phone]

        existing = Lawyer.objects.filter(phone=phone).first()
        if existing:
            self._cache[phone] = existing
            logger.info("复用已有律师", extra={"lawyer_id": existing.pk, "phone": phone})
            return existing

        real_name: str = data.get("real_name") or data.get("name") or phone
        username = self._unique_username(real_name)
        lawyer = Lawyer.objects.create_user(
            username=username,
            password=_DEFAULT_PASSWORD,
            real_name=real_name,
            phone=phone,
            is_active=True,
            is_admin=False,
            is_superuser=False,
        )
        self._cache[phone] = lawyer
        logger.info("创建新律师", extra={"lawyer_id": lawyer.pk, "username": username, "phone": phone})
        return lawyer

    def _unique_username(self, base: str) -> str:
        username = base
        counter = 2
        while Lawyer.objects.filter(username=username).exists():
            username = f"{base}_{counter}"
            counter += 1
        return username
