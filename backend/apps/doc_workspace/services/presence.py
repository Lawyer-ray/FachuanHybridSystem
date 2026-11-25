"""「这份文件现在有没有画布开着」——一个带 TTL 的在场登记。

## 为什么不能靠数据库里的会话行判断

`EditorSession` 是**持久**的：律师关掉标签页之后那行还在，`updated_at` 可能
只是几分钟前的一次保存。拿它当「画布开着」的证据会长期误判。

前端在 `OfficeView` 就绪时登记、每 30 秒续期、卸载时注销；后端只认 TTL 内的
登记。TTL 取 90 秒 = 3 个心跳周期，容忍一次丢包。

## 这个判断用来做什么

不是「决定写不写盘」，而是「写完盘要不要**同时**下发画布重放」。

- 画布开着 → 写盘 + 下发重放：律师立刻看到修订痕迹长出来，且即使重放失败
  （锚点漂移、插件没握手）磁盘上那份也已经是新的，不会丢。
- 画布没开 → 只写盘：没人需要重放。

**为什么不「画布开着就只写画布」**：重放是有失败率的（插件未握手、原文在编辑
过程中被改过）。只写画布意味着这次 AI 改动飘在内存里，律师一刷新就没了，而且
没有任何报错。落盘兜底的成本是一次原子写，换来的是「绝不因重放失败而丢内容」。
"""

from __future__ import annotations

from typing import Any

from django.core.cache import cache

#: 在场登记有效期（秒）。必须 > 前端心跳间隔，否则健康画布会周期性被判「没开」。
PRESENCE_TTL_SECONDS = 90

_KEY_PREFIX = "doc_workspace:canvas:"


def _key(kind: str, owner_id: int, subpath: str) -> str:
    return f"{_KEY_PREFIX}{kind}:{owner_id}:{subpath}"


def mark_open(*, kind: str, owner_id: int, subpath: str, user_id: int | None = None) -> None:
    """登记「我正在看这份文件的画布」（前端就绪时调，之后按心跳续期）。"""
    cache.set(_key(kind, owner_id, subpath), int(user_id or 0), timeout=PRESENCE_TTL_SECONDS)


def mark_closed(*, kind: str, owner_id: int, subpath: str) -> None:
    cache.delete(_key(kind, owner_id, subpath))


def is_open(*, kind: str, owner_id: int, subpath: str) -> bool:
    return cache.get(_key(kind, owner_id, subpath)) is not None


def snapshot_state() -> dict[str, Any]:
    """诊断用：当前有哪些画布登记在案（Admin/排查用，不进业务路径）。"""
    return {"ttl_seconds": PRESENCE_TTL_SECONDS}
