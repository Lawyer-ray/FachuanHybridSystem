"""案件列表轻量投影（``GET /api/v1/cases/cases?slim=true`` 的列表项形状）。

═══ 为什么单独一个 Schema，而不是给 CaseOut 加 exclude ═══
列表项有两个形状这件事必须**在 OpenAPI 里看得见**：端点声明
``response=list[CaseOut] | list[CaseSlimOut]``（与 ``/organization/lawyers`` 同一写法），
生成物里才会有任何一个数组的 anyOf，前端才知道「slim 的行到底有哪些键」。
用同一个 CaseOut + model_dump(exclude=...) 的话，生成物只有一个形状，
消费方只能靠注释猜「slim 时哪些键可能不在」，与「键在不在」这类漂移一起失控。

═══ 保留什么、剔除什么（依据：唯一的重消费方）═══
`frontend/src/features/bank-litigation/components/CaseListPage.tsx` 是列表页唯一
的消费方，它读的字段就是 `frontend/src/features/bank-litigation/types.ts` 里
`CaseRow` 的 7 个 Pick：id / name / status / current_stage / cause_of_action /
target_amount / filing_number。7 个嵌套集合（parties / assignments / logs /
case_numbers / supervising_authorities / chats / contacts）它一个都不读
（CaseListPage.tsx 全文没有这些名字）。

标量列不裁：CaseSlimOut 的标量字段与 CaseOut **完全一致**（同一份
`CASE_SCALAR_FIELDS`），多留标量的成本是 0——它们同在一行数据里，不额外发查询；
真正贵的是那 7 个嵌套集合（预取 10+ 条 SQL，真库单页 755KB）。
所以本合同可以一句话记住：**slim = CaseOut 去掉全部嵌套集合**。

═══ 为什么要 ``extra="forbid"`` ═══
端点响应是 ``list[CaseOut] | list[CaseSlimOut]``。pydantic 的 smart union 对
「全量 dict」会把 CaseSlimOut 也判为通过（多余键默认 ignore），实测直接吞掉全量
响应里的集合字段——默认行为被无声改掉。加上 extra="forbid" 后两个形状互斥：
全量 dict 只匹配 CaseOut，瘦身 dict 只匹配 CaseSlimOut。
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import ConfigDict

from .base import Case, ModelSchema
from .case_schemas import CASE_SCALAR_FIELDS, CaseOut

__all__: list[str] = ["CaseSlimOut"]


class CaseSlimOut(ModelSchema):
    """案件列表轻量投影：标量列与 CaseOut 一致，不含任何嵌套集合。

    中文标签口径必须与 CaseOut 一致（status / current_stage 走 get_*_display）：
    列表页拿 `c.status === '在办'` 判「待立案优先」、直接渲染 status 文案，
    返回代码值（active）会让这一页半英半中。两个 resolver 因此直接转调 CaseOut。
    """

    # 见模块头「为什么要 extra='forbid'」：让 union 的两个分支互斥
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    contract_id: int | None
    # 与 CaseOut 同口径下发：两份 schema 的标量列必须一致，否则「完整版有、瘦身版
    # 没有」的缺口会一个个冒出来（同 contract_id 当年的教训）。前端的程序线分组靠它。
    previous_case_id: int | None = None

    class Meta:
        model = Case
        fields: ClassVar = CASE_SCALAR_FIELDS

    @staticmethod
    def resolve_status(obj: Any) -> str | None:
        return CaseOut.resolve_status(obj)

    @staticmethod
    def resolve_current_stage(obj: Any) -> str | None:
        return CaseOut.resolve_current_stage(obj)

    @staticmethod
    def resolve_contract_id(obj: Any) -> int | None:
        return CaseOut.resolve_contract_id(obj)

    @staticmethod
    def resolve_previous_case_id(obj: Any) -> int | None:
        return CaseOut.resolve_previous_case_id(obj)
