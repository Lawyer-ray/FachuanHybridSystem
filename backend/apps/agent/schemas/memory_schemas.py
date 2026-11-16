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
