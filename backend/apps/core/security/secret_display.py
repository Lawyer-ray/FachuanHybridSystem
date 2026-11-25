"""敏感配置「已存值」的展示层：掩码概览 + 显式明文解密。

背景（v27.3.0 安全审计，主仓 #528 之后）：
`SystemConfig` 编辑页对 `is_secret` 项不再回显明文（`initial["value"]` 置空、
留空=不修改）。安全上是对的，但代价是管理员**完全看不到自己存了什么**——
连「存了几个 Key、每个多长」都无从确认，只能去翻数据库或凭记忆。

这里补两层，职责都很窄：

1. `describe_stored_value()`：常驻的掩码概览（前 4 后 4 + 长度 + 分段计数），
   任何时刻都不含完整明文，可以随页面一起渲染；
2. `reveal_stored_value()`：只在管理员**显式动作**时调用才返回明文；之所以留在这里
   而不是调用方直接 `SecretCodec().decrypt()`，是为了把「解密失败」收敛成一个可展示
   的错误类型（换过 `.env` 主密钥 / 密文损坏是最常见的两个现场）。

缓存头、二次确认、审计日志由调用方（Admin 视图）负责，本模块不碰 ORM 与视图。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from cryptography.fernet import InvalidToken

from apps.core.security.secret_codec import SecretCodec

#: 多值分隔符：换行 / 逗号 / 分号。
#: 与 `SystemConfigAdminForm._MULTI_KEY_CONFIGS` 的多 Key 口径保持一致，
#: 否则「保存时说 3 个、查看时说 1 个」会让人以为值被吞了。
_SEGMENT_SPLIT = re.compile(r"[\r\n,;]+")

#: 掩码保留的首尾字符数（与原 changelist 掩码口径一致）
_KEEP_HEAD = 4
_KEEP_TAIL = 4

#: 解密失败原因 → 给管理员看的可执行提示
_FAILURE_MESSAGES = {
    "missing_key": "未配置 CREDENTIAL_ENCRYPTION_KEY：服务端无法解密该配置（值仍在库里，密文完好）",
    "bad_cipher": "密文与当前主密钥不匹配：多半是换过 .env 的 CREDENTIAL_ENCRYPTION_KEY，需重新填一次该值",
}


class SecretValueUndecryptable(Exception):
    """密文无法解密（主密钥缺失 / 不匹配 / 数据损坏）。"""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(_FAILURE_MESSAGES.get(reason, "密文无法解密"))


def _split_segments(text: str) -> list[str]:
    """按多值分隔符切分并去掉空段。"""
    return [part.strip() for part in _SEGMENT_SPLIT.split(text) if part.strip()]


def mask_segment(segment: str) -> str:
    """单段掩码：长度 > 8 保留前 4 后 4，否则整段打码。"""
    if len(segment) > _KEEP_HEAD + _KEEP_TAIL:
        return f"{segment[:_KEEP_HEAD]}{'*' * (len(segment) - _KEEP_HEAD - _KEEP_TAIL)}{segment[-_KEEP_TAIL:]}"
    return "*" * len(segment)


def _decrypt_with_reason(raw_value: str) -> tuple[str | None, str]:
    """解密：返回 (明文或 None, 失败原因)。未加密的值原样返回。"""
    codec = SecretCodec()
    if not codec.is_encrypted(raw_value):
        return raw_value, ""
    try:
        return codec.decrypt(raw_value), ""
    except RuntimeError:
        return None, "missing_key"
    except (InvalidToken, ValueError, TypeError, UnicodeDecodeError):
        # InvalidToken（签名不匹配）/ base64 报错（binascii.Error 是 ValueError 子类）/ 非 UTF-8 明文
        return None, "bad_cipher"


@dataclass(frozen=True)
class StoredValueDescription:
    """已存值的展示快照。`segments` 对敏感项永远是掩码，可以安全渲染进 HTML。"""

    is_secret: bool
    decrypt_failed: bool = False
    failure_reason: str = ""
    segment_count: int = 0
    plain_length: int = 0
    segments: tuple[str, ...] = ()
    segment_lengths: tuple[int, ...] = ()
    display: str = ""

    @property
    def is_multi(self) -> bool:
        return self.segment_count > 1

    @property
    def failure_message(self) -> str:
        return _FAILURE_MESSAGES.get(self.failure_reason, "")

    @property
    def summary(self) -> str:
        """一行概览：多值时给个数，单值时给长度。"""
        if self.decrypt_failed:
            return "无法解密"
        if not self.segment_count:
            return "未设置"
        if self.is_multi:
            return f"共 {self.segment_count} 个值（每个 {self.segment_lengths[0]} 字符）"
        return f"长度 {self.plain_length} 字符"


def describe_stored_value(raw_value: str | None, *, is_secret: bool) -> StoredValueDescription:
    """把库里的原值（可能是密文）整理成可安全渲染的展示快照。"""
    raw = str(raw_value or "")
    if not raw:
        return StoredValueDescription(is_secret=is_secret, display="未设置")

    plain, failure_reason = _decrypt_with_reason(raw)
    if plain is None:
        return StoredValueDescription(
            is_secret=is_secret,
            decrypt_failed=True,
            failure_reason=failure_reason,
            display="无法解密",
        )

    segments = _split_segments(plain)
    if not segments:
        segments = [plain]

    shown = tuple(mask_segment(segment) for segment in segments) if is_secret else tuple(segments)
    display = f"已配置 {len(segments)} 个值" if len(segments) > 1 else shown[0]
    return StoredValueDescription(
        is_secret=is_secret,
        segment_count=len(segments),
        plain_length=len(plain),
        segments=shown,
        segment_lengths=tuple(len(segment) for segment in segments),
        display=display,
    )


def mask_summary(raw_value: str | None) -> str:
    """单行摘要：多值显示「已配置 N 个值」，单值显示掩码（changelist「配置值」列用）。"""
    return describe_stored_value(raw_value, is_secret=True).display


def count_segments(raw_value: str | None) -> int:
    """多值配置已存的分段数；解密失败或空值时返回 0。"""
    return describe_stored_value(raw_value, is_secret=True).segment_count


def value_cell(raw_value: str | None, *, is_secret: bool, limit: int = 50) -> tuple[str, str]:
    """列表页单元格：(显示文本, hover 全文)。

    - 敏感项：`已配置 N 个值` 或单段掩码；**title 恒空**，不泄露任何片段
    - 非敏感项：超长时截断，全文放 title（列表页原来截断后没有 title，看不到全文）
    - 空值：返回 ("", "")，由模板决定显示「未设置」
    """
    raw = str(raw_value or "")
    if not raw:
        return "", ""
    if is_secret:
        desc = describe_stored_value(raw, is_secret=True)
        if desc.decrypt_failed:
            return desc.failure_message, ""
        return desc.display, ""
    if len(raw) > limit:
        return f"{raw[:limit]}…", raw
    return raw, ""


def reveal_stored_value(raw_value: str | None) -> str:
    """解密并返回完整明文。失败抛 `SecretValueUndecryptable`，由调用方决定怎么提示。"""
    raw = str(raw_value or "")
    if not raw:
        return ""
    plain, failure_reason = _decrypt_with_reason(raw)
    if plain is None:
        raise SecretValueUndecryptable(failure_reason)
    return plain


__all__ = [
    "SecretValueUndecryptable",
    "StoredValueDescription",
    "count_segments",
    "describe_stored_value",
    "mask_segment",
    "mask_summary",
    "reveal_stored_value",
    "value_cell",
]
