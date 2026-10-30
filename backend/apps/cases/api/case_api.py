"""
案件 API

异步端点，Service 层同步调用通过 sync_to_async 包装。
所有 ORM 访问和 Pydantic 序列化均在 sync_to_async 闭包内完成，
防止 SynchronousOnlyOperation 和 Django Ninja re-validation 时的懒加载。

search / list 端点已补 response=list[CaseOut] 声明（openapi 生成物需要响应形状）：
_schema.py 内相关嵌套 Schema 均已支持 dict re-validation（resolver 带 dict 分支、
datetime 字段用 datetime | str 保留 mode="json" 的 ISO 字符串原样透传），
响应体与裸 dict 路径逐字节一致。get/create/update 仍不使用 response= 注解
（与 contracts 端点保持一致，避免 Ninja 对已序列化的 dict 做 re-validation）。
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.cases.schemas import CaseCreateFull, CaseFullOut, CaseIn, CaseOut, CaseUpdate
from apps.cases.services import CaseService
from apps.core.dto.request_context import extract_request_context

router = Router()

# 未显式传 limit 时的默认上限：宽过滤（如 status=active）也不能全表序列化
CASES_DEFAULT_LIMIT = 200
# 显式 limit 的硬上限（向后兼容：上限内任意 limit 均生效）
CASES_MAX_LIMIT = 2000


def _serialize_case(case: Any) -> dict:
    """将 Case 模型序列化为 JSON 安全的 dict（在 sync 上下文内完成 from_orm + dump）。

    返回 dict 让 Ninja 直接 JSON 序列化。from_orm 在 sync 上下文完成所有 ORM 访问。
    """
    return CaseOut.from_orm(case).model_dump(by_alias=True, mode="json")


def _get_case_service() -> CaseService:
    from apps.contracts.services.contract.wiring import get_contract_service

    return CaseService(contract_service=get_contract_service())


def _get_case_query_facade() -> CaseService:
    return _get_case_service()


def _get_case_mutation_facade() -> CaseService:
    return _get_case_service()


@router.get("/cases/search", response=list[CaseOut], by_alias=True)
async def search_cases(  # pragma: no cover
    request: HttpRequest,
    q: str,
    limit: int | None = 10,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """搜索案件(offset 供 MCP 信封 truncated=true 时续取,不传行为不变)"""
    service = _get_case_query_facade()
    ctx = extract_request_context(request)

    def _do() -> list[dict[str, Any]]:
        cases = list(
            service.search_cases(
                query=q,
                limit=limit,  # type: ignore[arg-type]
                offset=offset,
                user=ctx.user,
                org_access=ctx.org_access,
                perm_open_access=ctx.perm_open_access,
            )
        )
        return [_serialize_case(c) for c in cases]

    return await sync_to_async(_do)()


@router.get("/cases", response=list[CaseOut], by_alias=True)
async def list_cases(  # pragma: no cover
    request: HttpRequest,
    case_type: str | None = None,
    status: str | None = None,
    case_number: str | None = None,
    contract_id: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """获取案件列表（contract_id 可按合同过滤，供前端详情按需加载）

    限额策略（返回信封保持裸数组，供前端 workbench/material-prep 现状消费）：
    - 显式传 limit 时按它截断，上限 2000（向后兼容，上限内任意 limit 均生效）；
    - 未传 limit 时应用默认上限 200——含带过滤参数的宽过滤（如 status=active），
      防止单请求全表序列化。窄过滤消费方（contract_id 明细）结果集远小于 200，不受影响。
    - offset（默认 0）供 MCP 信封 truncated=true 时续取；不传行为不变。
    """
    service = _get_case_query_facade()
    ctx = extract_request_context(request)
    if limit is not None:
        effective_limit: int | None = max(1, min(limit, CASES_MAX_LIMIT))
    else:
        effective_limit = CASES_DEFAULT_LIMIT
    bounded_offset = max(0, offset)

    def _do() -> list[dict[str, Any]]:
        if case_number:
            raw = list(
                service.search_by_case_number(
                    case_number=case_number,
                    user=ctx.user,
                    org_access=ctx.org_access,
                    perm_open_access=ctx.perm_open_access,
                )
            )
        else:
            qs = service.list_cases(
                case_type=case_type,
                status=status,
                contract_id=contract_id,
                user=ctx.user,
                org_access=ctx.org_access,
                perm_open_access=ctx.perm_open_access,
            )
            sliced = qs[bounded_offset : bounded_offset + effective_limit] if effective_limit is not None else qs
            raw = list(sliced)
        return [_serialize_case(c) for c in raw]

    return await sync_to_async(_do)()


@router.post("/cases/full")
async def create_case_full(request: HttpRequest, payload: CaseCreateFull) -> dict[str, Any]:  # pragma: no cover
    """创建完整案件（包含当事人、指派、日志）"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)
    actor_id = getattr(ctx.user, "id", None) if ctx.user else None

    data: dict[str, Any] = {
        "case": payload.case.model_dump(),
        "parties": [p.model_dump() for p in payload.parties] if payload.parties else [],
        "assignments": [a.model_dump() for a in payload.assignments] if payload.assignments else [],
        "logs": [log.model_dump() for log in payload.logs] if payload.logs else [],
        "supervising_authorities": (
            [s.model_dump() for s in payload.supervising_authorities] if payload.supervising_authorities else []
        ),
    }

    def _create_full() -> dict[str, Any]:
        result = service.create_case_full(data, actor_id=actor_id, user=ctx.user)
        # ⚠️ 这里不能直接 `CaseOut.from_orm(case)` 后把 ORM 列表塞进 CaseFullOut：
        #    bulk_create 出来的 parties/assignments 没预加载 client/lawyer 关联，
        #    ModelSchema 取 client_detail 时拿到的是 client_id 整数，会报十几个
        #    「client_detail.id Field required」然后 500（实测）。
        #    最稳的做法是**按 case_id 重新查一次**，拿到带 select_related 的对象，
        #    再走和 GET /cases/{id} 完全相同的序列化路径 —— 两条路径口径一致，
        #    也就不会出现「创建返回的和查询返回的不一样」。
        from apps.cases.models import Case

        fresh = (
            Case.objects.select_related("contract")
            .prefetch_related(
                "parties__client",
                "assignments__lawyer__law_firm",
                "logs",
                "case_numbers",
                "supervising_authorities",
            )
            .filter(pk=result["case"].pk)
            .first()
        )
        if fresh is None:
            from apps.core.exceptions import NotFoundError

            raise NotFoundError(message="案件创建后查询失败")
        return _serialize_case(fresh)

    return await sync_to_async(_create_full)()


@router.get("/cases/{case_id}")
async def get_case(request: HttpRequest, case_id: int) -> dict[str, Any]:  # pragma: no cover
    """获取单个案件"""
    service = _get_case_query_facade()
    ctx = extract_request_context(request)

    def _get() -> dict[str, Any]:
        case = service.get_case(
            case_id=case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
        return _serialize_case(case)

    return await sync_to_async(_get)()


@router.post("/cases")
async def create_case(request: HttpRequest, payload: CaseIn) -> dict[str, Any]:  # pragma: no cover
    """创建案件"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)
    data = payload.model_dump()

    def _create() -> dict[str, Any]:
        case = service.create_case(data, user=ctx.user)
        return _serialize_case(case)

    return await sync_to_async(_create)()


@router.put("/cases/{case_id}")
async def update_case(request: HttpRequest, case_id: int, payload: CaseUpdate) -> dict[str, Any]:  # pragma: no cover
    """更新案件"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)

    def _update() -> dict[str, Any]:
        case = service.update_case(
            case_id,
            data,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
        return _serialize_case(case)

    return await sync_to_async(_update)()


@router.delete("/cases/{case_id}")
async def delete_case(request: HttpRequest, case_id: int) -> dict[str, bool]:  # pragma: no cover
    """删除案件"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)

    await sync_to_async(service.delete_case)(
        case_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )

    return {"success": True}
