"""API schemas and serializers."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, ClassVar, Literal

from apps.core.models.enums import CaseStatus

from .assignment_schemas import CaseAssignmentCreate, CaseAssignmentOut
from .base import Case, CaseAssignment, CaseChat, CaseLog, CaseParty, ModelSchema, Schema
from .log_schemas import CaseLogCreate, CaseLogOut
from .number_schemas import CaseNumberIn, CaseNumberOut
from .party_schemas import CasePartyCreate, CasePartyOut
from .supervising_authority_schemas import SupervisingAuthorityIn, SupervisingAuthorityOut

logger = logging.getLogger("apps.cases.schemas")

try:
    from apps.contacts.schemas import CaseContactOut
except ImportError:
    # S29-01（2026-11-23 二轮审计）：原实现只在 except 里静默赋 None，联系人字段会无日志、
    # 无告警地降级成空数组（改 contacts 侧名称或引入循环 import 时「联系人集体消失」不可见）。
    # 降级分支保留（contacts 是可选域），但必经 WARNING。
    logger.warning("CaseContactOut 导入失败，CaseOut.contacts 将降级为空数组", exc_info=True)
    CaseContactOut = None  # type: ignore[assignment,misc]


class CaseIn(ModelSchema):
    """
    建案入参。

    `contract_id` 必须显式声明：`Case.contract` 是 FK，但 ModelSchema 的 fields
    白名单里没有它，而 `CaseCommandService.create_case` 读的正是 `data["contract_id"]`
    ——既拿它做合同有效性校验，也拿它解析并校验代理阶段。漏了这一个字段，
    REST 建出来的案件会挂空合同（前端「新建下一程序案件」等于白建）。
    """

    contract_id: int | None = None
    # 收案日期。模型上有默认值（date.today），但二审/执行这类后续程序常要回填
    # 真实收案日；不给这个字段就只能建完再去改，而 CaseUpdate 同样没有它。
    start_date: date | None = None

    class Meta:
        model = Case
        fields: ClassVar = [
            "name",
            "status",
            "is_filed",
            "case_type",
            "target_amount",
            "preservation_amount",
            "cause_of_action",
            "current_stage",
            "effective_date",
            "specified_date",
        ]


class CaseChatOut(ModelSchema):
    class Meta:
        model = CaseChat
        fields: ClassVar = ["id", "platform", "name", "is_active"]


# Case 自身的标量列（不含任何关联集合）。CaseOut 与 CaseSlimOut 共用这一份：
# 列表瘦身版（case_slim_schemas.py）裁掉的只有 7 个嵌套集合，标量列两边同口径，
# 否则「slim 时 is_filed 怎么没了」这类缺口会逐个冒出来。
CASE_SCALAR_FIELDS: list[str] = [
    "id",
    "name",
    "status",
    "is_filed",
    "filing_number",
    "case_type",
    "start_date",
    "effective_date",
    "specified_date",
    "target_amount",
    "preservation_amount",
    "cause_of_action",
    "current_stage",
]


class CaseOut(ModelSchema):
    parties: list[CasePartyOut]
    assignments: list[CaseAssignmentOut]
    logs: list[CaseLogOut]
    case_numbers: list[CaseNumberOut]
    supervising_authorities: list[SupervisingAuthorityOut]
    chats: list[CaseChatOut]
    contract_id: int | None
    contacts: list[CaseContactOut] = []

    class Meta:
        model = Case
        fields: ClassVar = CASE_SCALAR_FIELDS

    @staticmethod
    def _resolve_list_field(obj: Any, key: str) -> list:
        """Common helper: return list data whether obj is a Django model, dict, or Pydantic model."""
        if isinstance(obj, dict):
            return obj.get(key, [])  # type: ignore[no-any-return]
        value = getattr(obj, key, None)
        if value is None:
            return []
        if hasattr(value, "all"):
            return list(value.all())  # Django QuerySet
        return list(value)  # Pydantic model field or plain list

    @staticmethod
    def resolve_parties(obj: Any) -> list:
        return CaseOut._as_party_dicts(CaseOut._resolve_list_field(obj, "parties"))

    @staticmethod
    def resolve_assignments(obj: Any) -> list:
        return CaseOut._as_assignment_dicts(CaseOut._resolve_list_field(obj, "assignments"))

    # ── 嵌套对象为什么要先转 dict ──
    #
    # CasePartyOut / CaseAssignmentOut 是 ModelSchema（ninja 的 ORM → schema 映射），
    # 它们的 `case` / `client` 外键会被渲染成 `case_id` / `client_id` 这两个整数键。
    # 而 resolve_* 返回的是**未序列化的 Django 模型实例**，pydantic 拿到实例后
    # 走的是 model_validate（不是 from_orm），取 `case_id` 时拿不到 ——
    # 报 5 个 "Field required" 然后接口 500。
    #
    # 实测：POST /cases/cases/full 一直 500，日志是
    #   5 validation errors for CaseFullOut / case.parties.0.case_id Field required
    # 而 GET /cases/{id} 不炸，因为它走 CaseOut.from_orm（orm_mode 生效）。
    # 这里显式把实例转成 ModelSchema 期望的 dict，两条路径就一致了。
    @staticmethod
    def _as_party_dicts(items: list) -> list:
        out = []
        for it in items or []:
            if isinstance(it, dict):
                out.append(it)
                continue
            d = {
                "id": getattr(it, "id", None),
                # ⚠️ 键名是 `case_id` / `client_id`（带 _id 后缀），
                #    不是 `case` / `client`。ModelSchema 把外键渲染成 `<field>_id`，
                #    写成 `case` 会继续报 "case_id Field required"——实测踩过。
                "case_id": getattr(it, "case_id", None),
                "client_id": getattr(it, "client_id", None),
                # ⚠️ 这里必须先翻成中文标签再放进 dict（见 _party_status_label）。
                "legal_status": CaseOut._party_status_label(it),
            }
            # client_detail 要的是**完整的 Client 对象**（ClientOut 有 id/name/... 一堆必填），
            # 只给 client_id 那个整数会让 resolver 拿到 DjangoGetter: 495，
            # 然后报十几个 "Field required"。这里把关联对象一起传给 resolver。
            d["client_detail"] = getattr(it, "client", None)
            d["client"] = getattr(it, "client", None)
            out.append(d)
        return out

    @staticmethod
    def _party_status_label(obj: Any) -> str:
        """`legal_status` 在**转 dict 这一步**就要翻成中文标签。

        为什么不能留给 `CasePartyOut.resolve_legal_status`：那个 resolver 的 dict 分支
        是直传（它假设传进来的 dict 已是序列化后的形状）。于是「原始模型 → dict」这一层
        放进去的是代码值（`plaintiff`），接口就原样吐英文。

        踩到过：案件卡上「诉讼地位」整行变成 `plaintiff：张三 / defendant：李四`，
        而同一张卡的 `status`（在办）、`current_stage`（一审）走 `get_*_display` 是中文，
        一张卡片上半中半英。tests/ci/unit/cases/test_case_schema_party_status.py 钉住这条。
        """
        raw = getattr(obj, "legal_status", None)
        if not raw:
            return ""
        getter = getattr(obj, "get_legal_status_display", None)
        if callable(getter):
            try:
                return str(getter())
            except (AttributeError, ValueError):  # pragma: no cover - 模型字段无 choices 时才会发生
                return str(raw)
        return str(raw)

    @staticmethod
    def _as_assignment_dicts(items: list) -> list:
        out = []
        for it in items or []:
            if isinstance(it, dict):
                out.append(it)
                continue
            out.append(
                {
                    "id": getattr(it, "id", None),
                    # 同上：键名带 _id 后缀
                    "case_id": getattr(it, "case_id", None),
                    "lawyer_id": getattr(it, "lawyer_id", None),
                    "lawyer_detail": getattr(it, "lawyer", None),
                }
            )
        return out

    @staticmethod
    def resolve_logs(obj: Any) -> list:
        return CaseOut._resolve_list_field(obj, "logs")

    @staticmethod
    def resolve_status(obj: Any) -> str | None:
        if isinstance(obj, dict):
            return obj.get("status")
        if hasattr(obj, "get_status_display"):
            return obj.get_status_display() if obj.status else None
        return getattr(obj, "status", None)

    @staticmethod
    def resolve_current_stage(obj: Any) -> str | None:
        if isinstance(obj, dict):
            return obj.get("current_stage")
        if hasattr(obj, "get_current_stage_display"):
            return obj.get_current_stage_display() if obj.current_stage else None
        return getattr(obj, "current_stage", None)

    @staticmethod
    def resolve_contract_id(obj: Any) -> int | None:
        if isinstance(obj, dict):
            return obj.get("contract_id")
        return getattr(obj, "contract_id", None)

    @staticmethod
    def resolve_case_numbers(obj: Any) -> list:
        return CaseOut._resolve_list_field(obj, "case_numbers")

    @staticmethod
    def resolve_supervising_authorities(obj: Any) -> list:
        return CaseOut._resolve_list_field(obj, "supervising_authorities")

    @staticmethod
    def resolve_chats(obj: Any) -> list:
        return CaseOut._resolve_list_field(obj, "chats")

    @staticmethod
    def resolve_contacts(obj: Any) -> list:
        # 降级分支的静默问题已在模块加载处用 WARNING 兜住（S29-01），此处不再逐条打日志
        if CaseContactOut is None:
            return []
        return CaseOut._resolve_list_field(obj, "contacts")


class CaseUpdate(Schema):
    name: str | None = None
    # 状态取值来自 Case 模型状态枚举（CaseStatus），非法值在入参校验阶段返回 422
    status: Literal[CaseStatus.ACTIVE, CaseStatus.CLOSED] | None = None
    is_filed: bool | None = None
    case_type: str | None = None
    target_amount: float | None = None
    preservation_amount: float | None = None
    cause_of_action: str | None = None
    current_stage: str | None = None
    effective_date: str | None = None


class CaseCreateFull(Schema):
    case: CaseIn
    parties: list[CasePartyCreate] | None = None
    assignments: list[CaseAssignmentCreate] | None = None
    logs: list[CaseLogCreate] | None = None
    case_numbers: list[CaseNumberIn] | None = None
    supervising_authorities: list[SupervisingAuthorityIn] | None = None


class CaseFullOut(Schema):
    case: CaseOut
    parties: list[CasePartyOut]
    assignments: list[CaseAssignmentOut]
    logs: list[CaseLogOut]
    case_numbers: list[CaseNumberOut]
    supervising_authorities: list[SupervisingAuthorityOut]


class LegalStatusItem(Schema):
    value: str
    label: str


class UnifiedGenerateRequest(Schema):
    template_id: int | None = None
    function_code: str | None = None
    client_id: int | None = None
    client_ids: list[int] | None = None
    mode: str | None = None


__all__: list[str] = [
    "CASE_SCALAR_FIELDS",
    "CaseChatOut",
    "CaseCreateFull",
    "CaseFullOut",
    "CaseIn",
    "CaseOut",
    "CaseUpdate",
    "LegalStatusItem",
    "UnifiedGenerateRequest",
]
