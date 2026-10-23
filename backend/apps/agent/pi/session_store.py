"""pi 原生 session 存储 —— 把上下文管理交还给 pi。

## 为什么改（原方案的问题）

旧实现用 ``--no-session``：pi 每请求新进程、零记忆，多轮上下文靠
``services/history.py`` 把历史渲染成一段 transcript 拼在 prompt 前。代价：

- **丢消息边界**：工具调用史被压成纯文本，模型用不上原生 tool-call 协议；
- **每次重发全量**：前缀每轮都变，prompt cache 打不中；
- **硬截断**：30 条 / 24000 字符封顶，超了就丢最旧，没有任何摘要；
- **无 compaction**：长会话只能靠人删会话重开。

现在改为 pi 原生 session：由 pi 负责上下文裁剪与自动 compaction
（``docs/compaction.md``），Django 的消息表继续作为**审计与回放**的权威。

## 三个实测约束（都是真的踩过）

1. **``--session-id <id>`` 按 project（cwd）隔离**：同一个 id 在不同 cwd 下
   会得到两个独立文件，模型完全丢失记忆。所以 cwd 必须**稳定**，不能是
   每请求新建的临时目录。
2. **``PI_CODING_AGENT_DIR`` 一改，sessions 也跟着走**：把配置目录和 session
   目录分开设是没用的，pi 会忽略 ``--session-dir``。所以两者都落在同一个
   稳定根目录下（见 :func:`layout`）。
3. **没有可用模型时 pi 直接退出、不写 session 文件**：所以「文件不存在」
   不能当成错误，只表示这轮没跑起来。

## 为什么 session id 就是 Django 的 session_id

一一对应带来三个好处：按会话定位文件（排查 / 清理）、删除会话时级联清理、
多 worker 共享同一目录时天然不会串会话。UUID 只含字母数字和 ``-``，
符合 pi 对 id 的字符要求。

## 部署要求（多 worker）

session 目录必须被所有 worker 共享（NFS / 挂载卷），否则同一会话落到不同
worker 时模型看到的是两段互不相干的历史。单机多 worker 天然满足。
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

#: 稳定根目录的环境变量（配置 + sessions 都在它下面）
ROOT_ENV = "FACHUAN_AGENT_HOME"
#: 缺省根目录（相对 backend 目录之外的用户级位置，避免误入 git）
DEFAULT_ROOT_NAME = ".fachuan-agent"


def agent_home() -> Path:
    """稳定根目录：配置（models.json / mcp.json / AGENTS.md）与 sessions 的父目录。

    优先 ``FACHUAN_AGENT_HOME``；否则落在 ``~/.fachuan-agent``。
    目录权限设为 0700——里面含 models.json（真实 API key）。
    """
    configured = os.environ.get(ROOT_ENV, "").strip()
    root = Path(configured).expanduser() if configured else Path.home() / DEFAULT_ROOT_NAME
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        logger.debug("无法收紧 %s 权限（忽略）", root, exc_info=True)
    return root


def layout() -> tuple[Path, Path, Path]:
    """返回 ``(work_dir, config_dir, sessions_dir)``。

    - ``work_dir``：pi 的 cwd。必须稳定——``--session-id`` 按 cwd 隔离会话，
      换成临时目录会让同一会话变成两个互不相干的历史。
    - ``config_dir``：``PI_CODING_AGENT_DIR``，放 models.json / mcp.json /
      AGENTS.md / settings.json。
    - ``sessions_dir``：pi 的 session 文件目录。
    """
    root = agent_home()
    work = root / "work"
    config = root / "config"
    sessions = root / "sessions"
    for path in (work, config, sessions):
        path.mkdir(parents=True, exist_ok=True)
    return work, config, sessions


def session_dir_for(session_id: str) -> Path:
    """某个 Django 会话对应的 pi session 文件目录。

    按会话分目录而不是全塞一起：删除会话时直接 rmtree，不用按 id 匹配文件名
    （文件名是 ``<时间戳>_<id>.jsonl``，前缀不可靠）。
    """
    path = layout()[2] / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_files(session_id: str) -> list[Path]:
    """该会话的 pi session 文件（通常 1 个）。"""
    directory = layout()[2] / session_id
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.jsonl"))


def has_session(session_id: str) -> bool:
    """是否已有可续写的历史（决定用 ``--session-id`` 续写还是新建）。"""
    return bool(session_files(session_id))


def delete_session(session_id: str) -> int:
    """删除某个会话的 pi session 文件，返回删除的文件数。

    删除 Django 会话时必须调用：否则磁盘上会留下模型上下文（含工具调用参数
    与工具返回内容），用户以为「会话已删」但数据还在。
    """
    directory = layout()[2] / session_id
    if not directory.is_dir():
        return 0
    removed = len(list(directory.glob("*.jsonl")))
    shutil.rmtree(directory, ignore_errors=True)
    if removed:
        logger.info("已清理 pi session 文件 session=%s files=%s", session_id, removed)
    return removed


def purge_orphans(valid_ids: set[str]) -> int:
    """清理不属于任何现存 Django 会话的 session 目录（运维/定时任务用）。

    Args:
        valid_ids: 仍需保留的 session_id 集合。

    Returns:
        删除的目录数。
    """
    root = layout()[2]
    removed = 0
    for child in root.iterdir():
        if not child.is_dir() or child.name in valid_ids:
            continue
        shutil.rmtree(child, ignore_errors=True)
        removed += 1
    if removed:
        logger.info("已清理 %s 个孤儿 pi session 目录", removed)
    return removed
