"""技能子域的常量与身份口径（一处定义，其余模块只引用）。

## key 与 name 必须分开

``key`` 是**身份**：``builtin:<name>``（随代码发布的目录）或 ``skill:<uuid>``
（数据库行）。``name`` 是**命令名**：slug，同时是 ``/skill:`` 的展开名。三级
作用域下同名是常态，用名字做身份必然打架（改一次名就断偏好与审计链），所以
偏好、API 路径、修订链一律用 ``key``。

## 为什么 ``NAME_RE`` 比「字母数字连字符」更严

``name`` 不只是本仓库的字符串：它会被拼进 ``/skill:<name>`` 指令、进系统提示、
在 MCP 工具里当参数。pi 1.6.0 的 ``dist/core/skills.js`` 对技能名有自己的校验
（禁止 ``--``、禁止首尾 ``-``），我们这边放行、pi 那边告警的话，同一条技能在
管理抽屉里「合法」、在运行时被静默丢弃——这是最难查的一类不一致。所以校验
规则必须**严于或等于** pi，两边同源维护（``mcp_server/tools/core/agent_skills.py``
的 ``_NAME_RE`` 与本处逐字一致）。
"""

from __future__ import annotations

import re

#: 合法技能名：小写字母/数字/连字符，必须以字母或数字开头结尾，**不得**出现连续
#: 连字符。禁 ``--`` 与首尾 ``-`` 是对齐 pi ``skills.js`` 的 ``validateName``。
#: 与 ``mcp_server/tools/core/agent_skills.py`` 的 ``_NAME_RE`` 同源。
NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9]|-(?!-)){0,62}[a-z0-9]$|^[a-z0-9]$")

#: 个人技能配额（超限拒绝创建，见 services/skills/user_skills.py）
MAX_USER_SKILLS = 20
#: 共享技能配额：按作用域分别计数（团队 30 / 所内 60）
MAX_SHARED_SKILLS: dict[str, int] = {"team": 30, "law_firm": 60}
#: 单技能正文上限：与注入/索引开销挂钩，超限拒绝保存
MAX_BODY_BYTES = 32 * 1024
#: 路由描述：单行，会进系统提示
MAX_DESCRIPTION = 400
#: 显示名上限
MAX_TITLE = 64
#: 保留版本数（保存后裁剪，见 ``review.prune_revisions``）
MAX_REVISIONS = 20

#: 单次正文分段的字节上限。取值必须 < MCP 侧 20480B 的拦腰截断线
#: （``mcp_server/server.py``），并给工具输出留出 JSON 包装的余量。
CONTENT_PAGE_BYTES = 16_000
#: 系统提示里的技能索引总预算（字）。≈1.5k token，是「每轮固定成本」的上限。
SKILL_INDEX_BUDGET = 4000
#: 索引里单条描述的截断长度（超出的部分只影响索引，不影响 ``get_agent_skill`` 全文）
PER_ITEM_DESCRIPTION_MAX = 220

#: 前缀：内置技能来自文件，个人/共享技能来自数据库
BUILTIN_PREFIX = "builtin:"
USER_PREFIX = "skill:"

#: 与前端内置 `/` 命令抢名的禁用词（避免个人技能把系统命令顶掉）
RESERVED_COMMANDS = frozenset(
    {"compact", "help", "skill", "model", "clear", "new", "status", "review", "manage-skills"}
)

#: 同名级联的优先级：数值小者胜（个人 > 团队 > 所内）。
SCOPE_RANK = {"lawyer": 0, "team": 1, "law_firm": 2}

#: 内置技能的权重。内置名是保留字、个人技能不得占用，所以内置不参与级联；
#: 单独给它一个 -1 是为了让 ``(scope_weight, name)`` 一处排序就能得到稳定顺序
#: （内置排在最前），不必在排序函数里分两段写。
BUILTIN_RANK = -1

#: 作用域 → 索引/徽标里的中文标签（``expand`` 与 ``prompt_block`` 共用一份）
SCOPE_LABELS: dict[str, str] = {
    "builtin": "内置",
    "lawyer": "我的",
    "team": "团队",
    "law_firm": "所内",
}

#: 作用域 → 排序权重（含内置）。``resolve`` 输出条目里的 ``scope_weight`` 就是它。
SCOPE_WEIGHT: dict[str, int] = {"builtin": BUILTIN_RANK, **SCOPE_RANK}
