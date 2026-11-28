"""个人技能的物化落盘（pi 只认目录 ``<dir>/SKILL.md``，``--skill`` 收目录）。

## 目录布局与权限

```
$FACHUAN_AGENT_HOME/skills/<user_id>/<name>/SKILL.md   # 目录 0700，文件 0600
```

按 ``user_id`` 隔离是硬要求：``--no-skills`` 是安全边界，物化目录只能在
``$FACHUAN_AGENT_HOME``（0700）下，且不同律师的目录互不可见。**不按 scope 分
目录**——目录名必须等于 ``/skill:`` 命令名，而命令名在解析后已唯一。

## 写盘纪律

- **幂等**：字节未变不重写（同一用户多栏并答会重复调用，白写一次就是白刷 mtime）。
- **原子**：临时文件 + ``os.replace``，并发读不会读到半截。
- **fail-soft**：``OSError`` 由调用方（``user_skills`` / ``skills_reconcile``）记
  ``logger.warning``，**不回滚 DB**——DB 是权威，磁盘只是缓存，下一轮
  ``enabled_skill_paths`` 会跳过缺失目录，``skills_reconcile`` 可重建。
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path

from apps.agent.models import AgentSkill
from apps.agent.pi.session_store import agent_home

from .constants import NAME_RE
from .render import render_skill_md

logger = logging.getLogger(__name__)

#: ``$FACHUAN_AGENT_HOME`` 下的技能物化目录
SKILLS_DIR_NAME = "skills"
SKILL_FILE_NAME = "SKILL.md"


def root_path(lawyer_id: int) -> Path:
    """某律师的物化根目录路径（**不建目录、不写盘**）。

    读路径（``enabled_skill_paths``）只能用这个：它跑在每轮对话的热路径上，
    磁盘异常不能让整轮挂掉；建目录留给写路径 ``root_for``。
    """
    return agent_home() / SKILLS_DIR_NAME / str(int(lawyer_id))


def root_for(lawyer_id: int) -> Path:
    """某律师的物化根目录（按 user_id 隔离，0700）；不存在就建。"""
    root = root_path(lawyer_id)
    _ensure_dir(root)
    return root


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        logger.warning("无法收紧 %s 权限（忽略）", path, exc_info=True)


def _skill_dir(lawyer_id: int, name: str) -> Path:
    """拼技能目录；``name`` 来自数据库，这里再挡一次路径穿越。"""
    if not NAME_RE.fullmatch(name or ""):
        raise ValueError(f"非法技能名: {name!r}")
    path = root_for(lawyer_id) / name
    # 同名目录被换成 symlink 时拒绝写入：否则 os.replace 会跟着链接写到别处
    # （只有同 OS 用户能构造，但修一次是一次的便宜钱）。
    if path.is_symlink():
        raise ValueError(f"技能目录是符号链接，拒绝写入: {path}")
    return path


def write_skill(skill: AgentSkill) -> Path:
    """把一条 ``AgentSkill`` 物化成 ``<root>/<name>/SKILL.md``，返回目录。"""
    if skill.lawyer_id is None:
        raise ValueError(f"技能 {skill.name!r} 没有所属律师，无法物化")
    return write_content(int(skill.lawyer_id), skill.name, skill.description, skill.body)


def write_content(lawyer_id: int, name: str, description: str, body: str) -> Path:
    """按原始字段物化（on_commit 回调里用：不把模型实例带出事务）。

    调用方负责 ``transaction.on_commit`` 与异常兜底；本函数只保证原子写。
    """
    content = render_skill_md(name, description, body)
    directory = _skill_dir(lawyer_id, name)
    _ensure_dir(directory)
    target = directory / SKILL_FILE_NAME

    encoded = content.encode("utf-8")
    existing = _read_bytes(target)
    if existing == encoded:
        return directory

    tmp = directory / f"{SKILL_FILE_NAME}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        with open(tmp, "wb") as handle:
            handle.write(encoded)
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return directory


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def remove_skill(lawyer_id: int, name: str) -> bool:
    """删掉一个物化目录；不存在返回 ``False``（幂等）。"""
    directory = _skill_dir(lawyer_id, name)
    if not directory.is_dir():
        return False
    shutil.rmtree(directory)
    return True


def prune(lawyer_id: int, keep: set[str]) -> list[str]:
    """删掉不在 ``keep`` 里的物化目录，返回被删的名字（按名字排序）。"""
    removed: list[str] = []
    for directory in sorted(root_for(lawyer_id).iterdir()):
        if not directory.is_dir() or directory.name in keep:
            continue
        shutil.rmtree(directory)
        removed.append(directory.name)
    return removed


def list_dirs(lawyer_id: int) -> list[str]:
    """某律师已有的物化目录名（按名字排序）。"""
    return sorted(path.name for path in root_for(lawyer_id).iterdir() if path.is_dir())


def list_user_ids() -> list[int]:
    """``skills/`` 下所有按 user_id 命名的目录（``skills_reconcile --prune`` 全量用）。"""
    base = agent_home() / SKILLS_DIR_NAME
    if not base.is_dir():
        return []
    return sorted(int(path.name) for path in base.iterdir() if path.is_dir() and path.name.isdigit())
