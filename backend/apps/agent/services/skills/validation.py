"""技能表单的归一化与校验（纯函数，无 IO、无 ORM）。

两段式：

1. ``normalize_payload`` 只做**无争议的收敛**（去 BOM、统一换行、去首尾空白），
   不改用户可见语义；创建与校验用同一份输入，预览才不会与实际落盘不一致。
   描述里的换行**刻意保留**给 ``validate_payload`` 判错——渲染时才折叠成单行。
2. ``validate_payload`` 返回字段级错误 ``[{field, message}]``，由 API 层拼成 422
   的可读消息。它不抛异常——``POST /skills/validate`` 要能一次列全所有问题。

保留名 = 内置技能名 ∪ 前端内置命令（``RESERVED_COMMANDS``）。内置技能名是保留字
的原因见 P0-BRIEF §1.3：`/skill:` 命令名在解析后必须唯一，内置技能不参与级联
去重，个人技能占用它就会静默顶掉随代码发布的那份。
"""

from __future__ import annotations

from collections.abc import Iterable

from .constants import (
    MAX_BODY_BYTES,
    MAX_DESCRIPTION,
    MAX_TITLE,
    NAME_RE,
    RESERVED_COMMANDS,
)
from .library import builtin_names


def normalize_payload(*, name: str | None, title: str, description: str, body: str) -> dict[str, str]:
    """表单 → 落库/渲染用的规范形态。"""
    return {
        "name": (name or "").strip(),
        "title": (title or "").strip(),
        "description": (description or "").strip(),
        "body": (body or "").replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").strip(),
    }


def reserved_names() -> set[str]:
    """个人技能不得占用的名字（内置技能名 + 前端内置命令）。"""
    return builtin_names() | RESERVED_COMMANDS


def validate_payload(
    payload: dict[str, str],
    *,
    require_name: bool = True,
    taken_names: Iterable[str] = (),
) -> list[dict[str, str]]:
    """字段级校验；``taken_names`` 是该用户已有的个人技能名（重名走 409）。"""
    errors: list[dict[str, str]] = []
    name = payload.get("name", "")
    if not name and require_name:
        errors.append({"field": "name", "message": "技能名不能为空"})
    elif name:
        errors.extend(_validate_name(name, taken_names))

    title = payload.get("title", "")
    if not title:
        errors.append({"field": "title", "message": "显示名不能为空"})
    elif len(title) > MAX_TITLE:
        errors.append({"field": "title", "message": f"显示名不能超过 {MAX_TITLE} 字"})

    description = payload.get("description", "")
    if not description:
        errors.append({"field": "description", "message": "描述不能为空（它决定 AI 什么时候用这个技能）"})
    elif "\n" in description or "\r" in description:
        errors.append({"field": "description", "message": "描述必须是单行（会写进系统提示）"})
    elif len(description) > MAX_DESCRIPTION:
        errors.append({"field": "description", "message": f"描述不能超过 {MAX_DESCRIPTION} 字"})

    body = payload.get("body", "")
    if not body:
        errors.append({"field": "body", "message": "正文不能为空"})
    elif len(body.encode("utf-8")) > MAX_BODY_BYTES:
        errors.append({"field": "body", "message": f"正文不能超过 {MAX_BODY_BYTES // 1024} KB"})
    return errors


def _validate_name(name: str, taken_names: Iterable[str]) -> list[dict[str, str]]:
    """名字相关错误：格式 / 保留字 / 与自己已有技能重名。"""
    if not NAME_RE.fullmatch(name):
        return [{"field": "name", "message": "技能名只能用 1-64 位小写字母、数字与连字符，且以字母或数字开头"}]
    if name in reserved_names():
        return [{"field": "name", "message": f"「{name}」是保留名（内置技能或系统命令），请换一个"}]
    if name in set(taken_names):
        return [{"field": "name", "message": f"你已有同名技能「{name}」"}]
    return []
