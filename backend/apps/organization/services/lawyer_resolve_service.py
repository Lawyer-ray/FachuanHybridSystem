"""律师 get_or_create 解析服务（用于 JSON 导入）。"""

from __future__ import annotations

import logging
from typing import Any

from django.utils.crypto import get_random_string

from apps.organization.models import Lawyer

logger = logging.getLogger("apps.organization")

# 初始密码长度（随机生成，含大小写字母与数字）
_INITIAL_PASSWORD_LENGTH = 12


def _generate_initial_password() -> str:
    """为导入创建的律师生成随机初始密码（安全审计：禁止硬编码弱密码）。"""
    return get_random_string(_INITIAL_PASSWORD_LENGTH)


class LawyerResolveService:
    """按 phone get_or_create Lawyer，维护会话内缓存避免重复创建。"""

    def __init__(self) -> None:
        self._cache: dict[str, Lawyer] = {}

    def resolve(self, data: dict[str, Any]) -> Lawyer | None:
        phone: str | None = data.get("phone")
        username: str | None = data.get("username")

        if not phone and not username:
            logger.warning("律师数据缺少 phone 和 username，跳过", extra={"data": data})
            return None

        # 优先按 phone 查找
        if phone:
            if phone in self._cache:
                return self._cache[phone]
            existing = Lawyer.objects.filter(phone=phone).first()
            if existing:
                self._cache[phone] = existing
                logger.info("复用已有律师", extra={"lawyer_id": existing.pk, "phone": phone})
                return existing  # type: ignore[no-any-return]

        # phone 找不到时按 username 查找（不创建新账号，避免覆盖系统账号）
        if username:
            cache_key = f"__username__{username}"
            if cache_key in self._cache:
                return self._cache[cache_key]
            existing = Lawyer.objects.filter(username=username).first()
            if existing:
                self._cache[cache_key] = existing
                logger.info("按 username 复用已有律师", extra={"lawyer_id": existing.pk, "username": username})
                return existing  # type: ignore[no-any-return]

        if not phone:
            logger.warning("律师数据缺少 phone 且 username 未找到，跳过", extra={"data": data})
            return None

        real_name: str = data.get("real_name") or data.get("name") or phone
        new_username = self._unique_username(real_name)
        lawyer = Lawyer.objects.create_user(
            username=new_username,
            password=_generate_initial_password(),
            real_name=real_name,
            phone=phone,
            is_active=True,
            is_admin=False,
            is_superuser=False,
        )
        self._cache[phone] = lawyer
        logger.info("创建新律师", extra={"lawyer_id": lawyer.pk, "username": new_username, "phone": phone})
        return lawyer  # type: ignore[no-any-return]

    def _unique_username(self, base: str) -> str:
        username = base
        counter = 2
        while Lawyer.objects.filter(username=username).exists():
            username = f"{base}_{counter}"
            counter += 1
        return username
