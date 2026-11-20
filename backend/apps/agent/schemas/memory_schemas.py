"""跨会话记忆的请求响应契约（个人管理 / 策展提升 / 注入快照 / 检索）。"""

from __future__ import annotations

from ninja import Schema

from ..models import AgentMemory


class MemoryOut(Schema):
    id: str
    scope: str
    kind: str
    content: str
    status: str
    confidence: float
    hit_count: int
    created_at: str
    source_session_id: str = ""
    #: 项目/案件锚点。两个都为 None 表示这是一条「跨项目通用」的记忆。
    contract_id: int | None = None
    case_id: int | None = None
    #: 非空 = 已有人点过确认，是「项目事实」；空 = 「同事的判断」。
    confirmed_at: str = ""
    confirmed_by: str = ""
    #: 本条推翻了哪条旧笔记（旧条不删除，只是不再注入）。
    supersedes_id: str = ""
    #: 本条**已被后来的条目推翻**。注入侧不会用它，但面板要标出来——
    #: 不然会并排显示两条互相矛盾的结论。
    is_superseded: bool = False


class ProjectNoteIn(Schema):
    """写一条项目笔记（挂到项目/某案件上，同团队成员都能看到）。"""

    content: str
    #: 至少给一个：只挂项目 = 整个项目通用；挂案件 = 只在该案会话里展开。
    contract_id: int | None = None
    case_id: int | None = None
    #: 不想传锚点时传会话 id，由服务端按会话归属反查（前端只有 sessionId，
    #: 拿不到 contract_id；让前端猜锚点必然写错地方）。会话不属于当前律师
    #: 时按「没给锚点」处理，不报越权细节。
    session_id: str | None = None
    kind: str = AgentMemory.Kind.FACT
    #: 推翻旧结论时传旧笔记 id：旧条保留、不再注入（不静默覆盖）。
    supersede_id: str | None = None


class NoteConfirmIn(Schema):
    """把一条笔记升为「项目事实」；``content`` 非空时顺手改写（律师说得更准）。"""

    content: str | None = None


class MemoryCreateIn(Schema):
    content: str
    kind: str = AgentMemory.Kind.FACT


class MemoryConfirmIn(Schema):
    ids: list[str]
    accept: bool = True


class PromoteCandidateOut(Schema):
    id: str
    kind: str
    content: str
    hit_count: int
    from_lawyer: str = ""
    pii_risk: list[str] = []


class PromoteIn(Schema):
    source_ids: list[str]
    content: str
    kind: str
    scope: str
    team_id: int | None = None
    #: 律所层必须显式传 True：表示已阅读「全所可见」的影响面声明。
    #: 为什么不是双管理员会签：实测生产环境存在只有 1 个管理员、甚至 0 个
    #: 管理员的律所（firm2/firm3/firm5），强制会签会让那些律所完全用不了
    #: 律所层。真实约束应该是「你知道自己在写全所规范」而不是「两个人盖章」。
    acknowledged_firm_wide: bool = False


class SnapshotOut(Schema):
    content: str


class MemoryHitOut(Schema):
    id: str
    scope: str
    kind: str
    content: str
    score: float
    #: 返回内容是否被截断。操作指引全文可达 8000 字，模型需要知道
    #: 自己看到的是否完整（不完整时应收窄查询或分批读取）。
    truncated: bool = False
