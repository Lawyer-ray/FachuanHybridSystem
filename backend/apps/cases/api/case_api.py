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
from django.http import HttpRequest, HttpResponse
from ninja import Router

from apps.cases.schemas import CaseCreateFull, CaseIn, CaseOut, CaseUpdate
from apps.cases.schemas.case_slim_schemas import CaseSlimOut
from apps.cases.services import CaseService
from apps.cases.services.log.case_log_query_service import warm_reminder_cache_for_cases
from apps.core.dto.request_context import extract_request_context

router = Router()

# 未显式传 limit 时的默认上限：宽过滤（如 status=active）也不能全表序列化
CASES_DEFAULT_LIMIT = 200
# 显式 limit 的硬上限（向后兼容：上限内任意 limit 均生效）
CASES_MAX_LIMIT = 2000


def _serialize_case(case: Any, *, slim: bool = False) -> dict:
    """将 Case 模型序列化为 JSON 安全的 dict（在 sync 上下文内完成 from_orm + dump）。

    返回 dict 让 Ninja 直接 JSON 序列化。from_orm 在 sync 上下文完成所有 ORM 访问。
    slim=True 走 CaseSlimOut（无嵌套集合），调用方的 queryset 必须同样是 slim 版本。
    """
    schema = CaseSlimOut if slim else CaseOut
    return schema.from_orm(case).model_dump(by_alias=True, mode="json")


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
        # S29-02（2026-11-23 二轮审计）：原实现序列化时每条日志的 reminders /
        # reminder_type / reminder_time 各发一次 Reminder 查询（200 案 × 每条日志
        # ≈ 上千次）→ 现在序列化前一次批量预热，序列化期零查询。
        warm_reminder_cache_for_cases(cases)
        return [_serialize_case(c) for c in cases]

    return await sync_to_async(_do)()


@router.get("/cases", response=list[CaseOut] | list[CaseSlimOut], by_alias=True)
async def list_cases(  # pragma: no cover
    request: HttpRequest,
    response: HttpResponse,
    case_type: str | None = None,
    status: str | None = None,
    case_number: str | None = None,
    contract_id: int | None = None,
    limit: int | None = None,
    offset: int = 0,
    slim: bool = False,
    with_total: bool = False,
    search: str | None = None,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    """获取案件列表（contract_id 可按合同过滤，供前端详情按需加载）

    限额策略（返回信封保持裸数组，供前端 workbench/material-prep 现状消费）：
    - 显式传 limit 时按它截断，上限 2000（向后兼容，上限内任意 limit 均生效）；
    - 未传 limit 时应用默认上限 200——含带过滤参数的宽过滤（如 status=active），
      防止单请求全表序列化。窄过滤消费方（contract_id 明细）结果集远小于 200，不受影响。
    - offset（默认 0）供 MCP 信封 truncated=true 时续取；不传行为不变。

    瘦身与总数（两个都是**可选增量**，不传时与历史响应逐字节一致）：
    - slim=true：列表项换成 CaseSlimOut（标量列与 CaseOut 同口径，剔除 7 个嵌套
      集合：parties / assignments / logs / case_numbers / supervising_authorities /
      chats / contacts）。预取同步裁剪，否则 SQL 一条也不省。
    - with_total=true：总量走**响应头 X-Total-Count**（真实总数，不受 limit/offset
      影响），响应体不变。

    服务端分页的两个下推参数（同样不传时行为不变）：
    - search=<kw>：name 或 cause_of_action 含关键词（icontains，大小写不敏感）。
    - sort=filable_first：待立案优先（无案号且 status=active 的排在前，同组内
      id DESC）；其他值一律当作没传，保持默认 -id。
    **为什么下推**：列表页要做服务端分页，如果关键词过滤与「待立案优先」还留在
    前端，它们只会作用于当前页——分页一上，前端过滤就是在错误的子集上过滤。
    两个参数都必须同时进 list_cases 与 count_cases（同一套过滤口径），否则
    X-Total-Count 与翻页对不上。case_number 分支保持历史行为（不切片、不排序），
    这两个参数只作用于列表分支。

    ╔═ 为什么不把裸数组改成 {items, total} 信封 ═╗
    ║ 本端点已有 4 个消费方直接按裸数组消费：                      ║
    ║   frontend/src/features/bank-litigation/api/cases.ts:29  listCases()  ║
    ║   frontend/src/features/workbench（按 contract_id 拉案件明细）      ║
    ║   frontend/src/features/material-prep                          ║
    ║   MCP 信封（旧 offset 续取路径）                                ║
    ║ 明文改信封 = 四个消费方同时红，且前端类型是生成物。总数是新增的     ║
    ║ 可选信息，放在响应头就能拿到，没必要为它换整个信封。              ║
    ╚════════════════════════════════════════════╝
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
                    slim=slim,
                )
            )
            total = len(raw)  # 案号分支不切片（历史行为），命中数就是总数
        else:
            qs = service.list_cases(
                case_type=case_type,
                status=status,
                contract_id=contract_id,
                user=ctx.user,
                org_access=ctx.org_access,
                perm_open_access=ctx.perm_open_access,
                slim=slim,
                search=search,
                sort=sort,
            )
            total = 0
            if with_total:
                # 切片之前取总量：总数是「过滤后的全集」，与 limit/offset 无关
                # search 必须同参传下去，否则搜索时 total 会恒为全集
                total = service.count_cases(
                    case_type=case_type,
                    status=status,
                    contract_id=contract_id,
                    user=ctx.user,
                    org_access=ctx.org_access,
                    perm_open_access=ctx.perm_open_access,
                    search=search,
                    sort=sort,
                )
            sliced = qs[bounded_offset : bounded_offset + effective_limit] if effective_limit is not None else qs
            raw = list(sliced)
        if not slim:
            # S29-02（2026-11-23 二轮审计）：原实现序列化时每条日志的 reminders /
            # reminder_type / reminder_time 各发一次 Reminder 查询（200 案 × 每条日志
            # ≈ 上千次）→ 现在序列化前一次批量预热，序列化期零查询。
            # slim=true 时响应里没有 logs，预热只会为每个案件多一次 logs 查询（纯 N+1）。
            warm_reminder_cache_for_cases(raw)
        if with_total:
            response["X-Total-Count"] = str(total)
        return [_serialize_case(c, slim=slim) for c in raw]

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
        # ⚠️ 这里不能直接 `CaseOut.from_orm(case)` 后把 ORM 列表塞进完整版输出：
        #    bulk_create 出来的 parties/assignments 没预加载 client/lawyer 关联，
        #    ModelSchema 取 client_detail 时拿到的是 client_id 整数，会报十几个
        #    「client_detail.id Field required」然后 500（实测）。
        #    最稳的做法是**按 case_id 重新查一次**，拿到带 select_related 的对象，
        #    再走和 GET /cases/{id} 完全相同的序列化路径 —— 两条路径口径一致，
        #    也就不会出现「创建返回的和查询返回的不一样」。
        #
        # 重查下沉到 Service 层（API 层禁止直接 ORM，见 four-layer.md）。
        fresh = service.get_case_model_with_relations(result["case"].pk)
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
        # S29-02（2026-11-23 二轮审计）：原实现单案详情同样按日志数发提醒查询
        # → 现在序列化前一次批量预热。
        warm_reminder_cache_for_cases([case])
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
