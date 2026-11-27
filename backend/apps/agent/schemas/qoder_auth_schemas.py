"""qoder 登录态契约（前端「登录 Qoder」按钮用）。

## 为什么登录要有一个专门的契约，而不是塞进 ``BackendOptionOut``

两者的生命周期不同：``BackendOptionOut`` 是**清单**（每次打开切换器拉一次），登录是
一次**有状态的流程**（点按钮 → 拿链接 → 轮询结果）。塞进清单会让「清单」承载一个
随时在变的字段，前端还得在清单轮询里做状态机。

``BackendOptionOut`` 只多一个 ``action``（"这一行需要用户点一下"），指向本模块的端点。
"""

from __future__ import annotations

from ninja import Schema


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
