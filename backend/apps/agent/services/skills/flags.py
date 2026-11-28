"""技能体系的总开关（回滚用，也是「降级不报错」的唯一入口）。

## 三档而不是布尔

只做「开/关」两档的话，出问题时的选择只有「全关」——那会一次性把律师已经写好的
技能、索引、抽屉全部隐身，比故障本身更让人慌。所以留一档 ``dry``：

- ``on``（缺省）：全功能。
- ``dry``：解析、API、抽屉、``/skill:`` 展开全部正常，**但不把索引块写进系统提示**。
  用来快速判断「是不是索引块把某一轮弄坏了」，而不影响律师点名使用与按需读取。
- ``off``：写接口 503、解析只返内置、索引块为空、``expand`` 只认内置。DB 数据完整保留，
  改回 ``on`` 立即恢复（下一轮就读到）。

环境变量叫 ``FACHUAN_AGENT_USER_SKILLS``，**刻意**与 ``FACHUAN_AGENT_SKILLS_DIR``
（内置技能目录，``library.py``）区分：后者是路径覆盖，两者同名会让人在排障时改错一个。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

ENV_VAR = "FACHUAN_AGENT_USER_SKILLS"

MODE_ON = "on"
MODE_DRY = "dry"
MODE_OFF = "off"
_VALID = (MODE_ON, MODE_DRY, MODE_OFF)

_warned = False


def user_skills_mode() -> str:
    """当前模式（``on`` / ``dry`` / ``off``）；非法值回落 ``on`` 并只告警一次。

    只告警一次是刻意的：这个函数在每轮对话的热路径上被调用，写错一个字会让日志
    被同一行刷满，反而盖住真正的错误。
    """
    global _warned
    raw = (os.environ.get(ENV_VAR) or "").strip().lower()
    if not raw:
        return MODE_ON
    if raw not in _VALID:
        if not _warned:
            _warned = True
            logger.warning("%s=%r 不是合法取值（%s），按 on 处理", ENV_VAR, raw, "/".join(_VALID))
        return MODE_ON
    return raw


def user_skills_enabled() -> bool:
    """用户/共享技能是否参与解析与交付（``off`` 时只剩内置）。"""
    return user_skills_mode() != MODE_OFF


def writes_enabled() -> bool:
    """写接口是否可用（``off`` 时一律 503：读保留取证，写停掉）。"""
    return user_skills_mode() != MODE_OFF


def prompt_block_enabled() -> bool:
    """是否把技能索引块注入系统提示（``dry`` 与 ``off`` 都不注入）。"""
    return user_skills_mode() == MODE_ON


def reset_cache() -> None:
    """清掉「已告警」标记（测试用：同一进程里要验证告警只出现一次）。"""
    global _warned
    _warned = False
