"""技能子域的常量与身份口径（一处定义，其余模块只引用）。

## key 与 name 必须分开

``key`` 是**身份**：``builtin:<name>``（随代码发布的目录）或 ``skill:<uuid>``
（数据库行）。``name`` 是**命令名**：slug，同时是物化目录名与 ``/skill:`` 的
展开名。三级作用域下同名是常态，用名字做身份必然打架（改一次名就断偏好与
审计链），所以偏好、API 路径、修订链一律用 ``key``。
"""

from __future__ import annotations

import re

#: 合法技能名：小写字母/数字/连字符（Agent Skills 规范），不含路径分隔符。
#: 与 mcp_server/tools/core/agent_skills.py 的 ``_NAME_RE`` 同构。
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

#: 个人技能配额（超限拒绝创建，见 services/skills/user_skills.py）
MAX_USER_SKILLS = 20
#: 单技能正文上限：与 pi 加载开销挂钩，超限拒绝保存
MAX_BODY_BYTES = 32 * 1024
#: 路由描述：单行，会进系统提示
MAX_DESCRIPTION = 400
#: 显示名上限
MAX_TITLE = 64
#: 保留版本数（保存后裁剪，见 user_skills._prune_revisions）
MAX_REVISIONS = 20

#: 前缀：内置技能来自文件，个人/共享技能来自数据库
BUILTIN_PREFIX = "builtin:"
USER_PREFIX = "skill:"

#: 与前端内置 `/` 命令抢名的禁用词（避免个人技能把系统命令顶掉）
RESERVED_COMMANDS = frozenset(
    {"compact", "help", "skill", "model", "clear", "new", "status", "review", "manage-skills"}
)

#: 同名级联的优先级：数值小者胜（个人 > 团队 > 所内）。
#: 内置名是保留字，个人技能不得占用，所以内置不参与级联。
SCOPE_RANK = {"lawyer": 0, "team": 1, "law_firm": 2}
