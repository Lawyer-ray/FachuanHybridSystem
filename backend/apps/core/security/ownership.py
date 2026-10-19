"""「按创建人归属」的行级查询口径（解耦 2026-10-19）。

document_parsing.record_ownership_q 与 document_recognition.task_ownership_q
逐字相同（仅 docstring 不同），收敛为 core 共享函数；两个调用方保留原函数名
做薄包装，调用点零改动。口径：

- is_admin / is_superuser：全量可见（管理员监管视角），返回 None 表示无需过滤；
- 普通用户：仅可见自己创建的记录；存量 created_by 为 NULL 的旧记录
  （加归属字段前创建）保持所内可见，作为兼容旧数据的口径。
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q

from apps.core.security.admin_access import is_admin_user


def created_by_ownership_q(
    user: Any | None,
    *,
    field: str = "created_by",
    include_legacy_null: bool = True,
) -> Q | None:
    """返回按 ``field``（默认 created_by）归属过滤的 Q；管理员返回 None（全量）。

    include_legacy_null=False 时不再放行存量 NULL 行（新表无历史数据时用）。
    """
    if is_admin_user(user):
        return None
    q: Q = Q(**{field: user})
    if include_legacy_null:
        q |= Q(**{f"{field}__isnull": True})
    return q
