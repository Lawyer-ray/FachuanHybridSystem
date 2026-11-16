"""回调路由标识：把一次解析任务映射成云端回调里的 uid 片段。

MinerU 的 checksum 是 ``sha256(uid + seed + content)``，但回调本身**不带**
我们的 record id —— 只有 uid / seed / checksum / content。所以 uid 必须自己
带上定位信息，否则收到回调也不知道该写回哪条记录。

设计：``uid = f"dp-{record_id}-{随机后缀}"``
- 前缀 ``dp`` 是命名空间，避免与其他系统共用一个 MinerU 账号时串号；
- ``record_id`` 让回调 O(1) 定位到记录（不需要扫库匹配）；
- 随机后缀让 uid 不可预测：仅凭记录 id 猜不出合法 uid。伪造者仍须过
  checksum（需要我方配置的 uid 私钥 + 该记录的 seed）才可能写入。
"""

from __future__ import annotations

import secrets

#: uid 的正文前缀（``dp`` = document parsing）
_UID_PREFIX = "dp"

#: 随机后缀字节数
_UID_SUFFIX_BYTES = 6


def callback_uid(record_id: int) -> str:
    """为指定解析记录生成不重复的回调 uid。"""
    return f"{_UID_PREFIX}-{int(record_id)}-{secrets.token_hex(_UID_SUFFIX_BYTES)}"


def record_id_from_uid(uid: str) -> int | None:
    """从回调 uid 里取回解析记录 id；格式不合法返回 None。"""
    parts = (uid or "").strip().split("-")
    if len(parts) != 3 or parts[0] != _UID_PREFIX or not parts[1].isdigit():
        return None
    return int(parts[1])
