"""技能子域的领域错误（API 层负责翻译成 403/404/409/422/429）。

单独成模块而不塞进 ``user_skills``：API 只依赖错误类型、不依赖 CRUD 实现，
import 图更短，也避免「为了拿一个异常类把整个写路径拖进来」。
"""

from __future__ import annotations


class SkillError(Exception):
    """技能子域的领域错误基类。"""


class SkillNotFound(SkillError):
    """技能不存在或不属于当前律师（404，不区分两者：不泄漏存在性）。"""


class SkillForbidden(SkillError):
    """只读/越权操作（内置技能不可删、非内置不可复制 → 403）。"""


class SkillConflict(SkillError):
    """重名、版本冲突等（409）。"""


class SkillVersionConflict(SkillConflict):
    """``PUT`` 的 ``version`` 与库中不一致（409）。"""


class SkillQuotaExceeded(SkillError):
    """个人技能数超配额（429）。"""


class SkillInvalid(SkillError):
    """字段级校验失败（422）；``errors`` 供 API 拼可读消息。"""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        self.errors = errors
        super().__init__(as_message(errors))


def as_message(errors: list[dict[str, str]]) -> str:
    """字段级错误 → 一行可读消息（Ninja 没有统一错误体，保持简单）。"""
    return "；".join(f"{error['field']}: {error['message']}" for error in errors)
