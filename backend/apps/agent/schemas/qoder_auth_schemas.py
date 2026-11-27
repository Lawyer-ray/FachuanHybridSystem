"""qoder 登录态契约（前端「登录 Qoder」按钮用）。

## 为什么登录要有一个专门的契约，而不是塞进 ``BackendOptionOut``

两者的生命周期不同：``BackendOptionOut`` 是**清单**（每次打开切换器拉一次），登录是
一次**有状态的流程**（点按钮 → 拿链接 → 轮询结果）。塞进清单会让「清单」承载一个
随时在变的字段，前端还得在清单轮询里做状态机。

``BackendOptionOut`` 只多一个 ``action``（"这一行需要用户点一下"），指向本模块的端点。
"""

from __future__ import annotations

from ninja import Schema


class QoderAccountOut(Schema):
    """池子里的一个 qoder 账号（额度容器）。"""

    #: 账号 id（``default`` = 升级前那个单账号）
    id: str
    #: 显示名（来自凭据文件；取不到时由服务端编号成「账号 N」）
    name: str
    #: 现在能不能用（有凭据 且 不在冷却期）
    usable: bool
    #: 最近一次失败的人话（额度耗尽 / 登录失效）；空串 = 没出过错
    last_error: str = ""


class QoderAuthOut(Schema):
    """当前登录态（``GET /agent/qoder/auth``）。"""

    #: 现在能不能跑 qoder：配了显式令牌/密钥，或前端点过登录并成功。
    authenticated: bool
    #: 已登录账号的显示名（取不到为空串；不是邮箱也不是令牌）。
    account: str = ""
    #: 凭据来源：``token``（环境变量令牌/SA 密钥）/ ``login``（前端授权）/ ``none``。
    mode: str = "none"
    #: 面向用户的下一步（``authenticated=True`` 时为空串）。
    message: str = ""
    #: 账号池。额度是账号级的，所以池子里可以有多个（见后端 ``qoder_accounts``）。
    accounts: list[QoderAccountOut] = []


class QoderLoginIn(Schema):
    """发起一次授权。

    ``account_id`` 空 = **新增一个账号**（点一次登录往池子里加一个额度容器）；
    非空 = 给那个账号换令牌（登录失效后重登用）。
    """

    account_id: str = ""


class QoderLoginOut(Schema):
    """一次登录尝试的状态（``POST /agent/qoder/login`` 与轮询共用）。"""

    login_id: str
    #: ``waiting``（等人授权）/ ``success`` / ``failed`` / ``expired``（超时或会话失效）。
    state: str
    #: 浏览器授权链接。前端渲染成按钮，**不要截断**——参数丢一个就授权失败。
    url: str = ""
    #: 给人看的一句话（进行中 / 失败原因 / 成功提示）。
    message: str = ""
    #: 成功后带上账号名（取不到为空串）。
    account: str = ""
    #: 这次登录落到哪个账号上（前端据此提示「已添加账号」还是「已更新账号」）。
    account_id: str = ""
