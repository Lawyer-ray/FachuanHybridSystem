"""为 agent 工具调用铸造「当前律师」身份凭证。

## 背景（confused deputy）

MCP 工具最终经 REST API 访问数据。若 ``mcp_server`` 一律用服务账号（超管）
调用，任何律师都能借 agent 之名读到全所数据，写操作的审计也记在服务账号
名下。这里在**每轮对话**开始前为发起会话的律师铸一个 access token：

    chat_service ──铸 token──▶ pi 进程 env（FACHUAN_USER_TOKEN）
        └─ mcp.json: "Authorization": "Bearer ${FACHUAN_USER_TOKEN}"（pi 展开 env）
              └─ mcp_server.identity 透传 ──▶ REST API（JWTOrSessionAuth）

工具从此以律师本人身份执行：归属过滤、权限、审计与该律师直接登录完全一致，
378 个工具一行不用改。

## 凭证形态

- 无状态 access token，寿命同全局 ``ACCESS_TOKEN_LIFETIME``（前端拿到的是同一种
  票），每轮重铸；单轮 agent 运行远短于该寿命。
- 不发 refresh token：改密失效机制（``pwd_ver``）只需作用在 refresh 上，access
  的暴露窗口由寿命收敛。
- token 只存在于 pi 子进程 env 与临时目录里 mcp.json 的 **env 变量引用**中，
  不落盘明文；临时目录随请求结束 rmtree。

无用户身份（``user_id`` 为空，仅测试/脚本场景）时不铸 token，``mcp_server``
回退服务账号。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: pi 子进程 env 里承载律师 access token 的变量名（mcp.json 以 ``${...}`` 引用）
USER_TOKEN_ENV = "FACHUAN_USER_TOKEN"


def _load_active_user(user_id: int) -> Any:
    """按 id 取**已激活**用户；取不到或已停用一律抛错（调用方 fail-closed）。

    用 ``get_user_model()`` 而非 import ``Lawyer``：与 ``core.security.auth`` 同口径，
    且避免 agent → organization 的跨模块 Model 导入。
    """
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    user = user_model.objects.get(pk=user_id)
    if not getattr(user, "is_active", False):
        raise ValueError(f"用户已停用，拒绝签发 agent 凭证: {user_id}")
    return user


def mint_user_access_token(user_id: int) -> str:
    """为律师铸 access token（同步 ORM，async 上下文须经 ``sync_to_async``）。

    Raises:
        用户不存在 / 已停用时抛 ``DoesNotExist`` / ``ValueError``，由调用方拒绝本轮对话。
    """
    from ninja_jwt.tokens import AccessToken

    user = _load_active_user(user_id)
    # ignore[misc]: 同 token_exchange_service——mypy 对 for_user 的已知误报
    return str(AccessToken.for_user(user))  # type: ignore[misc]
