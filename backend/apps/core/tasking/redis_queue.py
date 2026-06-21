"""Redis 任务队列管理服务。

提供对 Django Q Redis broker 中排队任务的查看、删除、清空操作。
仅在 Redis broker 激活时可用（即 REDIS_URL 已配置）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger("apps.core.tasking")


@dataclass
class QueuedTask:
    """从 Redis 队列中反序列化的任务信息。"""

    index: int
    task_id: str
    name: str
    func: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    started: datetime | None
    raw: str  # 原始签名字符串，用于 LREM 定位


def _get_redis_connection() -> Any:
    """获取 Django Q 使用的 Redis 连接。"""
    from django_q.conf import Conf

    if not getattr(Conf, "REDIS", None):
        return None

    import redis

    return redis.Redis.from_url(Conf.REDIS)


def _get_queue_key() -> str:
    """获取 Redis 队列的 key 名称。"""
    from django_q.conf import Conf

    return f"django_q:{Conf.CLUSTER_NAME}:q"


def is_redis_broker() -> bool:
    """检查当前是否使用 Redis 作为 Django Q broker。"""
    from django_q.conf import Conf

    return bool(getattr(Conf, "REDIS", None))


def get_queue_length() -> int:
    """获取队列中的待处理任务数量。"""
    conn = _get_redis_connection()
    if conn is None:
        return 0
    key = _get_queue_key()
    return int(conn.llen(key))


def list_tasks(limit: int = 200) -> list[QueuedTask]:
    """列出队列中的任务（不移除）。

    Args:
        limit: 最多返回的任务数量

    Returns:
        按入队顺序排列的任务列表
    """
    conn = _get_redis_connection()
    if conn is None:
        return []

    key = _get_queue_key()
    raw_items = conn.lrange(key, 0, limit - 1)
    if not raw_items:
        return []

    from django_q.signing import SignedPackage

    tasks: list[QueuedTask] = []
    for idx, raw_bytes in enumerate(raw_items):
        try:
            raw_str = raw_bytes.decode("utf-8") if isinstance(raw_bytes, bytes) else raw_bytes
            task_dict: dict[str, Any] = SignedPackage.loads(raw_str)
            tasks.append(
                QueuedTask(
                    index=idx,
                    task_id=task_dict.get("id", ""),
                    name=task_dict.get("name", ""),
                    func=task_dict.get("func", ""),
                    args=task_dict.get("args", ()),
                    kwargs=task_dict.get("kwargs", {}),
                    started=task_dict.get("started"),
                    raw=raw_str,
                )
            )
        except Exception:
            logger.warning("Failed to deserialize queued task at index %d", idx, exc_info=True)
            tasks.append(
                QueuedTask(
                    index=idx,
                    task_id="(decode error)",
                    name="(decode error)",
                    func="",
                    args=(),
                    kwargs={},
                    started=None,
                    raw="",
                )
            )
    return tasks


def delete_task_by_index(index: int) -> bool:
    """根据队列位置删除单个任务。

    Redis LREM 通过值匹配删除，所以需要先定位到对应 raw bytes。

    Args:
        index: 任务在队列中的位置（0-based）

    Returns:
        是否成功删除
    """
    conn = _get_redis_connection()
    if conn is None:
        return False

    key = _get_queue_key()
    raw_bytes = conn.lindex(key, index)
    if raw_bytes is None:
        return False

    removed = conn.lrem(key, 1, raw_bytes)
    return bool(removed > 0)


def delete_tasks_by_ids(task_ids: set[str]) -> int:
    """根据 task_id 批量删除任务。

    策略：读取全部 -> 过滤 -> 删除 key -> 重新推入幸存者。

    Args:
        task_ids: 要删除的 task_id 集合

    Returns:
        成功删除的数量
    """
    conn = _get_redis_connection()
    if conn is None:
        return 0

    key = _get_queue_key()
    all_raw = conn.lrange(key, 0, -1)
    if not all_raw:
        return 0

    from django_q.signing import SignedPackage

    survivors: list[bytes] = []
    removed = 0

    for raw_bytes in all_raw:
        try:
            raw_str = raw_bytes.decode("utf-8") if isinstance(raw_bytes, bytes) else raw_bytes
            task_dict = SignedPackage.loads(raw_str)
            if task_dict.get("id") in task_ids:
                removed += 1
            else:
                survivors.append(raw_bytes)
        except Exception:
            survivors.append(raw_bytes)

    # 原子替换：先删再推（非事务性，但 Django Q worker 会容忍空队列）
    conn.delete(key)
    if survivors:
        conn.rpush(key, *survivors)

    return removed


def purge_queue() -> int:
    """清空整个队列。

    Returns:
        被清除的任务数量
    """
    conn = _get_redis_connection()
    if conn is None:
        return 0

    key = _get_queue_key()
    count = int(conn.llen(key))
    if count > 0:
        conn.delete(key)
    return count
