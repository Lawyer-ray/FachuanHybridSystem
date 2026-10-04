"""法院短信提交幂等去重（delivery_event_key 生成与查重）。

CourtSMS.delivery_event_key 配合唯一约束 uniq_courtsms_delivery_event_key，
用于拦截「同一条短信在短时间内重复提交」造成的重复处理副作用
（重复下载、重复 CaseLog、重复群通知）。

语义约定：
- 幂等键 = sha256(时间窗桶 + 短信内容)。时间按窗口取整参与哈希，
  同一内容在窗口内的重复提交（转发器重试、收件箱重复点击）生成相同键；
- 查重时同时检查「当前桶 + 上一桶」，覆盖提交时间跨窗口边界的场景；
- 隔天重发的相同文本落在不同时间桶，键不同，不会被误挡。
"""

from __future__ import annotations

import hashlib
from datetime import datetime

# 同一内容在该窗口（秒）内的重复提交视为同一条送达事件
DUPLICATE_WINDOW_SECONDS = 600


def _bucket_index(received_at: datetime) -> int:
    """把接收时间映射到去重时间窗桶（窗口取整）"""
    return int(received_at.timestamp()) // DUPLICATE_WINDOW_SECONDS


def _hash_bucket_content(bucket: int, content: str) -> str:
    digest = hashlib.sha256(f"{bucket}|{content}".encode(), usedforsecurity=False)
    return digest.hexdigest()


def build_delivery_event_key(content: str, received_at: datetime) -> str:
    """生成入库用的幂等键（sha256 十六进制，64 字符，与字段 max_length 一致）"""
    return _hash_bucket_content(_bucket_index(received_at), content)


def build_lookup_keys(content: str, received_at: datetime) -> list[str]:
    """生成查重键列表（当前桶 + 上一桶，覆盖跨窗口边界提交）"""
    bucket = _bucket_index(received_at)
    return [_hash_bucket_content(bucket, content), _hash_bucket_content(bucket - 1, content)]
