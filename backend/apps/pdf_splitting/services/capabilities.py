"""部署能力自检：这台机器上「哪些能力真的能用」，不能用的话该去改哪一项配置。

## 为什么需要它

本仓至少有四类能力是**配错了就静默空转**的，症状统一是「律师说功能没用，管理员翻日志」：

- 多引擎分歧裁定（``OCR_JUDGE_ENABLED`` + ``OCR_JUDGE_API_KEY``）：没开 / 缺 Key 时每条
  分歧都直接进人工清单，界面上分不清「环境没配」与「真的没裁定」；
- DeepSeek OCR（``DEEPSEEK_OCR_API_KEY``）：没配 Key 时它连 ``auto`` 顺序都进不去，而在
  「解析平台」里**锁定**它会在起跑线上就失败（v27.26.1 起的契约）；
- MinerU / Textin（``DocumentParseProvider`` 行）：一条都没启用时全部退回本地 OCR，
  生僻字与印章的错率与云端不同，但日志里只有一句「未配置任何解析平台」。

本模块把这件发现动作前移到一句自检：**谁不能用、缺什么、去哪改**。同源 idiom 见
:mod:`apps.core.utils.migration_health`（启动期 WARNING 列表，绝不阻断启动）。

## 边界

- **纯读**：不写库、不改配置、不发任何外部请求；
- **不许抛**：自检崩了比没有自检更糟（``smoke_check`` 会因此假红，运维把它塞进
  ``--skip-*`` 之后就再也不看了）。读配置 / 读 provider 失败一律降级成「该项不可用」+
  一条 note，见 :data:`_READ_ERRORS`；
- **不重写判据**：``judge`` 走 :func:`disagreement_judge.gate_state`，云端平台走
  :func:`parser_factory.resolve_cloud_backends`，本模块只把它们的答案翻成一句人话。
  判据留在原处，否则两处口径迟早分叉——届时自检说「可用」而任务说「未配置」，
  比没有自检更难查。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import DatabaseError

from apps.document_parsing.services import parser_factory
from apps.pdf_splitting.services.split import disagreement_judge

logger = logging.getLogger(__name__)

#: 自检 fail-open 兜底收的异常类型（**故意不写裸 ``except Exception``**：pre-commit 的
#: broad-except 棘轮只许下调，见 ``devtools/security_guard.py --check broad-except``）。
#: 列出的这些都实测会从下面两条读路径冒出来：``DatabaseError`` 是配置表 / provider 表读不到
#: （真实事故形态），``RuntimeError`` 是 pytest-django 拒绝无库访问、``ImportError`` 是后端
#: 模块缺依赖、``OSError`` 是连接与磁盘层，其余四种是配置值或 provider 行结构不符。
_READ_ERRORS = (
    DatabaseError,
    ImportError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
    KeyError,
    AttributeError,
)

#: ``judge.reason`` 平时**一律**是 ``disagreement_judge.GATE_*``（原因码集合归它所有）；
#: 只有「连门禁都读不出来」时由本模块给出这个值。刻意不往 gate 的原因码集合里加成员：
#: 那个集合进了任务 ``summary``、前端按它分支，加一个成员要连带改前端。
JUDGE_REASON_UNREADABLE = "unreadable"

# ── note 文案：每条一句话 = 谁 / 缺什么 / 去哪改 ──────────────────────────────
#
# 顺序即严重度，``deployment_capabilities()`` 按这个顺序拼 ``notes``：
# ① 分歧裁定没生效（配了却没开 / 开了却没 Key）→ ② 云端取字整链不可用 →
# ③ 只有一个平台缺 Key。同一档里「缺 Key」排在「没开开关」前面：前者是漏填，
# 后者多半是没打算开。
NOTE_JUDGE_MISSING_KEY = "多引擎分歧裁定未生效：未配置 OCR_JUDGE_API_KEY（系统配置 → 分类 ocr）。分歧全部进人工清单。"
NOTE_JUDGE_GATE_OFF = "多引擎分歧裁定未开启：OCR_JUDGE_ENABLED=0（系统配置 → 分类 ocr）。"
NOTE_JUDGE_UNREADABLE = (
    "多引擎分歧裁定状态读取失败（读系统配置出错）；本次自检按未生效处理，分歧全部进人工清单。"
    "修：确认数据库与系统配置可读后重跑 smoke_check。"
)
NOTE_CLOUD_ALL_UNAVAILABLE = (
    "云端取字全部不可用：MinerU / Textin 未启用，DeepSeek 未配 Key。当前只能走本地 OCR（生僻字与印章易错）。"
)
NOTE_DEEPSEEK_MISSING_KEY = "DeepSeek OCR 未配 Key；在「解析平台」里锁定它会直接失败（v27.26.1 起的契约）。"
NOTE_ENGINES_UNREADABLE = (
    "云端取字平台状态读取失败（读解析平台配置出错）；本次自检按全部不可用处理。"
    "修：确认数据库与「解析平台」管理页可读后重跑 smoke_check。"
)


def deployment_capabilities() -> dict[str, Any]:
    """只读：当前部署到底能用哪些能力，不能用的原因是啥、该去改哪一项。

    Returns:
        固定三键的字典：

        - ``judge``：``{"enabled": bool, "reason": str}``，``reason`` 取自
          :func:`disagreement_judge.gate_state` 的原因码（读不出来时是
          :data:`JUDGE_REASON_UNREADABLE`）；
        - ``engines``：``{"mineru": bool, "textin": bool, "deepseek": bool}``；
        - ``notes``：每条一句人话（谁 / 缺什么 / 去哪改），按严重度排序；
          **全部可用时是空列表**。

        本函数不抛异常：读配置 / 读 provider 失败会降级成对应项不可用 + 一条 note。
    """
    judge, judge_note = _judge_capability()
    engines, engine_notes = _cloud_engines_capability()
    notes: list[str] = ([judge_note] if judge_note else []) + engine_notes
    result: dict[str, Any] = {"judge": judge, "engines": engines, "notes": notes}
    return result


def _judge_capability() -> tuple[dict[str, Any], str | None]:
    """``judge`` 项 + 它自己那条 note（可用时为 ``None``）。

    判据只有 :func:`disagreement_judge.gate_state` 一处：它已经区分 ``gate_off``（没开
    总闸）与 ``missing_key``（开了却忘填 Key）——这两个状态让运维去改的是**两个不同配置项**，
    所以这里只把原因码翻成对应文案，绝不自己再判一遍。
    """
    try:
        enabled, reason = disagreement_judge.gate_state()
    except _READ_ERRORS:
        logger.warning("部署能力自检：读取分歧裁定门禁失败，按未生效处理", exc_info=True)
        return {"enabled": False, "reason": JUDGE_REASON_UNREADABLE}, NOTE_JUDGE_UNREADABLE

    if enabled:
        return {"enabled": True, "reason": reason}, None
    if reason == disagreement_judge.GATE_MISSING_KEY:
        return {"enabled": False, "reason": reason}, NOTE_JUDGE_MISSING_KEY
    if reason == disagreement_judge.GATE_OFF:
        return {"enabled": False, "reason": reason}, NOTE_JUDGE_GATE_OFF
    # 其它原因码（如任务级的 ``not_requested``，正常情况下不会从部署级门禁出现）只回状态、
    # 不猜 note：宁可少一句解释，也不要给运维指错一个配置项。
    return {"enabled": False, "reason": reason}, None


def _cloud_engines_capability() -> tuple[dict[str, bool], list[str]]:
    """``engines`` 项 + 它的 note 列表。

    「能不能用」的判据只有 :func:`parser_factory.resolve_cloud_backends` 一处——它返回的
    就是**当前可用**的平台列表（MinerU / Textin 看 ``DocumentParseProvider`` 行，DeepSeek
    看 ``DEEPSEEK_OCR_API_KEY``）。本函数刻意不再自己读一遍 SystemConfig 或 provider 表。
    """
    try:
        available = set(parser_factory.resolve_cloud_backends(parser_factory.AUTO_BACKEND))
    except _READ_ERRORS:
        logger.warning("部署能力自检：读取云端解析平台失败，按全部不可用处理", exc_info=True)
        return dict.fromkeys(parser_factory.CLOUD_BACKEND_CHOICES, False), [NOTE_ENGINES_UNREADABLE]

    engines = _engines_from(available)
    if not any(engines.values()):
        return engines, [NOTE_CLOUD_ALL_UNAVAILABLE]
    if not engines.get("deepseek", False):
        # 其他平台至少一个可用：不是「整链没了」，而是「别去锁那一个」。
        return engines, [NOTE_DEEPSEEK_MISSING_KEY]
    return engines, []


def _engines_from(available: set[str]) -> dict[str, bool]:
    """把「可用平台名集合」翻成固定三键的布尔表（键取自 ``CLOUD_BACKEND_CHOICES``）。"""
    return {name: name in available for name in parser_factory.CLOUD_BACKEND_CHOICES}
