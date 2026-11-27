"""UI 动作回执 / 页面状态快照（前端 → 后端）的请求契约。

字段名与取值是**双端冻结契约**：模型侧看到的是 ``publish_ui_action`` 的返回值
（``apps/agent/services/ui_action/__init__.py``），前端侧提交的是这里。改字段要两端同改。

## 为什么这里要做清洗，而不是信任前端

``detail`` / ``observed_location`` 是浏览器里算出来的产物，最终会被**原样转述进模型
上下文**、也会进日志。不洗的话有两个具体后果：

1. 换行/回车能把一句「已跳到 /projects」伪造成两条记录（模型会照着转述给律师）；
2. 终端转义序列能改写日志行——审计链路里的「谁让 AI 干了什么」就此失真。

所以按不可信输入处理：去控制字符、截断，不拒收。截断而不拒收的理由是这两个字段
只是**解释性**的——少一段尾巴不影响「成没成」，而拒收会让一次真实执行的结果整份丢掉。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from ninja import Schema
from pydantic import Field, field_validator, model_validator

from apps.core.security.scrub import scrub_for_storage

logger = logging.getLogger(__name__)

#: 控制字符（含 DEL）。
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
#: ``code`` / ``detail`` / ``observed_location`` / ``route`` / ``note`` 的长度上限。
_MAX_TEXT = 200
#: 页面状态快照序列化后的字符上限（超了直接拒，理由见 :class:`UiSnapshotIn`）。
_MAX_SNAPSHOT_STATE = 2000
#: 单个动作名（``available_actions`` / ``blocked_actions[].name``）的长度上限（真名都是
#: ``ui_xxx`` 量级，64 字已经宽裕）。
_MAX_ACTION_NAME = 64
#: 两份动作列表（``available_actions`` / ``blocked_actions``）共用的条数上限：同页面的动作数远
#: 小于此，多了就是噪声而已。两端同一口径（前端 ``MAX_AVAILABLE_ACTIONS`` / ``MAX_BLOCKED_ACTIONS``）。
_MAX_ACTIONS = 10
#: 动作名的字符集：与 ``manifest`` 里的真名一致（小写 + 下划线）。``-`` / 空格 / 中文都不收——
#: 名字是**查表用的标识**，长得不像名字的只可能让模型去调一个不存在的动作。长度与
#: ``_MAX_ACTION_NAME`` 同源（写死两处的话，改一处就会静默多收或少收一档）。
_ACTION_NAME_RE = re.compile(rf"^[A-Za-z0-9_]{{1,{_MAX_ACTION_NAME}}}$")
#: ``call_id`` 只可能是后端自己生成的 32 位十六进制。仍然限字符集与长度：它会拼进
#: Redis 键、也会进日志行，放任任意字符串等于给人一个撑键名、改日志的口子。
_CALL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _untrusted_text(value: str) -> str:
    """前端产物 → 可安全转述的短文本（去控制字符 → 去首尾空白 → 截断）。"""
    return _CONTROL_RE.sub("", value or "").strip()[:_MAX_TEXT]


class UiActionResultIn(Schema):
    """前端提交一次 UI 动作的执行结果。

    ``outcome`` 用 ``Literal`` 而不是自由字符串：它不是给人看的说明，而是模型据以
    决定下一步的**状态机输入**（``ok`` 才能说「已完成」）。多一个拼写变体就等于
    多一条没人测过的分支，还会静默落进积压表被当成 ``unknown`` 转述出去。
    """

    #: 派发时 ``publish_ui_action`` 返回的那个 id（把回执与动作对上号的唯一依据）。
    call_id: str
    #: 页面执行的真实结局。``aborted`` = 律师离开页面/手动取消，不是失败。
    outcome: Literal["ok", "error", "aborted"]
    #: 失败原因码（如 ``route_unreachable``）。只在 ``error`` 时有意义。
    code: str = ""
    #: 给模型看的一句解释（可为空）。
    detail: str = ""
    #: 执行完成后页面的真实地址（``ok`` 时最能证明「页面到底在哪」）。
    observed_location: str = ""

    @field_validator("call_id")
    @classmethod
    def _check_call_id(cls, value: str) -> str:
        if not _CALL_ID_RE.match(value or ""):
            raise ValueError("call_id 不合法")
        return value

    @field_validator("code", "detail", "observed_location")
    @classmethod
    def _clean_untrusted(cls, value: str) -> str:
        return _untrusted_text(value)

    @model_validator(mode="after")
    def _drop_code_when_not_error(self) -> UiActionResultIn:
        """``code`` 只随 ``error`` 传递。

        前端若给 ``ok`` 也带上 code，模型会把「成功」和「路由不可达」同时读到——
        冻结契约里 ``code`` 仅 error 时出现，这里替前端守住那一半。
        """
        if self.outcome != "error":
            self.code = ""
        return self


class UiSnapshotIn(Schema):
    """前端回传的一次页面状态快照（``POST /agent/ui-snapshots/{request_id}``）。

    ``state`` 会被**原样拼进模型上下文**、也会进日志，所以与 ``detail`` 同口径按不可信
    输入处理：先脱敏（密钥类字段遮成 ``***``）再限量。

    **``state`` 超限直接拒、不截断**：截断后的结构体会缺键，而模型会把缺的键当成「页面上确实
    没有这个字段」——比拒绝更误导。拒绝时把实际字数与上限写进错误，页面作者据此收窄
    自己声明的字段（模型拿到的仍是「没问到」，不会变成假的空页面）。

    **``available_actions`` 相反：名字可以截断**（去控制字符 → strip → 截 64 字 → 丢空串
    → 去重 → 最多 10 条，超出只截断，不拒收）。两者口径不同是因为坏处的形状不同：名字是
    **查表用的不透明标识**，截短后匹配不到任何动作，模型也就不会（也无法）调它——失败方向是
    「少了一个提示」，**不构成假事实**；而截断状态会凭空造出「页面上没有这个字段」。所以前者
    容错、后者拒收。

    **``blocked_actions`` 同 ``available_actions`` 的口径**（清洗 + 截断 + 限量，不拒收）：它
    也是「查表用的标识 + 一句解释」，坏一条只少一条提示。但比名字多一条硬要求——``name`` 必须
    像真名（:data:`_ACTION_NAME_RE`），``reason`` 必须非空：一条「没有原因」的 blocked 项对模型
    等于「这条不许用」，它只会照此放弃，而律师看到的是 AI 莫名其妙不做。所以形状不对的项整条
    丢掉，而不是留个半句。
    """

    #: 页面主动声明的那部分状态（``ui-tools/page-state.ts`` 的注册表产物）。
    state: dict[str, Any] = Field(default_factory=dict)
    #: 页面此刻的真实地址（模型据此知道「看到的是哪一页」）。
    route: str = ""
    #: 页面明说「我没声明状态」时带这句话；后端据此回 ``no_page_state`` 而不是空对象。
    note: str = ""
    #: 本页**此刻可做**的动作名（manifest 的 ``name``）。让模型不用先试错再改口。
    available_actions: list[str] = Field(default_factory=list)
    #: 本页**有、但此刻做不了**的动作与原因（``[{"name", "reason"}]``）。与 ``available_actions``
    #: 互补：那边说能做，这边说做不了以及为什么（如「还没选中材料包」），模型据此先补前置。
    blocked_actions: list[dict] = Field(default_factory=list)

    @field_validator("route", "note")
    @classmethod
    def _clean_untrusted(cls, value: str) -> str:
        return _untrusted_text(value)

    @field_validator("available_actions")
    @classmethod
    def _clean_available_actions(cls, value: list[str]) -> list[str]:
        """名字列表按不可信文本洗一遍：模型会原样读到它们，但坏名字只会「查不到」。"""
        cleaned: list[str] = []
        for item in value:
            name = _CONTROL_RE.sub("", item or "").strip()[:_MAX_ACTION_NAME]
            if name and name not in cleaned:
                cleaned.append(name)
        if len(cleaned) > _MAX_ACTIONS:
            logger.warning(
                "页面快照的 available_actions 有 %d 条，超过 %d 条上限，已截断",
                len(cleaned),
                _MAX_ACTIONS,
            )
            return cleaned[:_MAX_ACTIONS]
        return cleaned

    @field_validator("blocked_actions")
    @classmethod
    def _clean_blocked_actions(cls, value: list[dict]) -> list[dict]:
        """``blocked_actions`` 按不可信文本洗一遍：形状不对的项**整条丢掉**，同名的只留第一条。

        丢而不拒：一条 bad 项只少一条提示；拒收则会让整份快照丢掉（连 ``available_actions``
        一起），模型退回「没问到」。多键的项也丢——多出来的键没人在前端填过，留着只会让模型
        以为契约里还有别的东西（而它没有）。
        """
        cleaned: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in value:
            if set(item) != {"name", "reason"}:
                continue
            raw_name, raw_reason = item["name"], item["reason"]
            if not isinstance(raw_name, str) or not isinstance(raw_reason, str):
                continue
            name = _CONTROL_RE.sub("", raw_name).strip()
            reason = _untrusted_text(raw_reason)
            if not _ACTION_NAME_RE.match(name) or not reason or name in seen:
                continue
            seen.add(name)
            cleaned.append({"name": name, "reason": reason})
        if len(cleaned) > _MAX_ACTIONS:
            logger.warning(
                "页面快照的 blocked_actions 有 %d 条，超过 %d 条上限，已截断",
                len(cleaned),
                _MAX_ACTIONS,
            )
            return cleaned[:_MAX_ACTIONS]
        return cleaned

    @model_validator(mode="after")
    def _check_state_size(self) -> UiSnapshotIn:
        self.state = scrub_for_storage(self.state)
        encoded = json.dumps(self.state, ensure_ascii=False)
        if len(encoded) > _MAX_SNAPSHOT_STATE:
            raise ValueError(
                f"页面状态序列化后 {len(encoded)} 字，超过 {_MAX_SNAPSHOT_STATE} 字上限，已拒绝（不静默截断："
                "缺键会被模型当成页面上确实没有该字段）。请页面只声明判断下一步真正要用的字段。"
            )
        return self
