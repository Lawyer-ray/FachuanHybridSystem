"""回调签名：MinerU checksum 校验、Textin 共享密钥签名，以及 seed 生成。

这些是纯函数（无 IO、无 DB），所以放在独立模块而不是某个 Service 类里——
接收端点和后端创建侧都要用，而两边不该互相 import。

MinerU 的算法来自其官方回调文档：``checksum = sha256(uid + seed + content)``，
其中 ``content`` 是回调 body 里 ``content`` 字段的**原文**（JSON 字符串），
**不是** HTTP 请求体——校验必须对原文做，先 parse 再序列化会因为空格/键序
变化算出不同的摘要。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

#: Textin 回调签名头名（本服务自定义约定，见 textin_backend 的说明）
TEXTIN_SIGNATURE_HEADER = "X-Webhook-Signature"

#: MinerU seed 的字节数（任意长度均可参与拼接，取 16 字节 hex 兼顾可读与不可猜）
_SEED_BYTES = 16


def generate_seed() -> str:
    """为单个任务生成回调 seed（MinerU 用它与我们派生的 uid 一起算 checksum）。"""
    return secrets.token_hex(_SEED_BYTES)


def mineru_checksum(uid: str, seed: str, content: str) -> str:
    """按 MinerU 约定算 checksum：``sha256(uid + seed + content)`` 的 16 进制小写。"""
    return hashlib.sha256(f"{uid}{seed}{content}".encode()).hexdigest()


def verify_mineru_checksum(*, uid: str, seed: str, content: str, checksum: str) -> bool:
    """常量时间比较 MinerU checksum；任一侧为空一律失败。"""
    if not uid or not seed or not checksum:
        return False
    expected = mineru_checksum(uid, seed, content)
    return hmac.compare_digest(expected, checksum.strip().lower())


def textin_signature(secret: str, raw_body: bytes) -> str:
    """Textin 回调签名：``sha256(secret || raw_body)`` 的 16 进制小写。

    用原始请求体而非解析后的 JSON，理由同 MinerU：签名对象必须是字节级原文。
    """
    return hashlib.sha256(secret.encode() + raw_body).hexdigest()


def verify_textin_signature(*, secret: str, raw_body: bytes, signature: str) -> bool:
    """常量时间比较 Textin 签名；secret 或签名头为空一律失败（fail-closed）。"""
    if not secret or not signature:
        return False
    expected = textin_signature(secret, raw_body)
    return hmac.compare_digest(expected, signature.strip().lower())
