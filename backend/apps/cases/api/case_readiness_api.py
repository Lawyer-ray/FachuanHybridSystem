"""案件就绪度相关 API：材料齐备度 / 起诉答辩条件 / 利益冲突预检.

这三个端点都是**只读判断**（GET 或 POST 但无副作用），
对应原型 detail.html 与 case-draft.html 里律师「决定下一步做什么」之前要看的三块信息：
  · GET  /{case_id}/material-status   这件能不能递立案（还缺哪一项材料）
  · GET  /{case_id}/readiness         起诉条件 / 答辩条件（按 current_stage 分流）
  · POST /{case_id}/conflict-check    当事人是否与既有客户/在办案件冲突

为什么 conflict-check 用 POST 而不是 GET：
  它要做一批跨表比对（当事人 × 客户库 × 在办案件），
  放在 GET 上会被浏览器/代理缓存，而冲突结论必须实时；
  同时便于将来加「记录一次预检」的审计日志。
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.cases.schemas import CaseReadinessOut, ConflictCheckOut, MaterialStatusOut
from apps.cases.services.case_readiness_service import CaseReadinessService, ConflictCheckService, MaterialStatusService
from apps.core.security import get_request_access_context

router = Router()


def _readiness() -> CaseReadinessService:
    return CaseReadinessService()


def _materials() -> MaterialStatusService:
    return MaterialStatusService()


def _conflict() -> ConflictCheckService:
    return ConflictCheckService()


@router.get("/{case_id}/material-status", response=MaterialStatusOut)
def case_material_status(request: HttpRequest, case_id: int) -> Any:  # pragma: no cover
    """案件材料齐备度。

    返回每类材料的 ok/stale/miss/na 状态与齐备计数。
    律师最常问的是「这件能不能递」，所以单独给 `ready`（只看 miss，stale 不阻塞）。
    """
    get_request_access_context(request)  # 触发鉴权上下文，非法用户直接 401/403
    # 槽位按案件当前阶段自动选：一审问「合同/借据/流水/催收」，
    # 二审问「一审判决书/上诉状/答辩状/一审卷宗」。两套不可混用，
    # 混了就会出现「二审案缺催收记录」这种律师一眼看穿的错。
    return _materials().status_of(case_id, mode=_materials().mode_of(case_id))


@router.get("/{case_id}/readiness", response=CaseReadinessOut)
def case_readiness(request: HttpRequest, case_id: int) -> Any:  # pragma: no cover
    """案件就绪度（起诉条件 / 答辩条件）。

    **按 current_stage 给不同的一组校验**：
      一审未立案 → filing 模式（主体/管辖/时效/材料/金额）
      二审及以后 → appeal 模式（前序案件/二审案号/一审判决书/材料）
      其他阶段   → other 模式（暂无专门校验，明确返回空而不是假装通过）
    """
    get_request_access_context(request)
    return _readiness().readiness_of(case_id)


@router.post("/{case_id}/conflict-check", response=ConflictCheckOut)
def case_conflict_check(request: HttpRequest, case_id: int) -> Any:  # pragma: no cover
    """利益冲突预检。

    三档判定（不要一律当冲突，否则律师会对告警脱敏）：
      red     同名且证件号相同 → 同一人在对方阵营，必须停
      yellow  同名但证件号不同 → 疑似重名，需律师复核
      neutral 缺证件号无法判定 → 提示补全资料，不是冲突
    `blocked=True` 表示存在 red 级命中，前端据此阻断后续动作。
    """
    get_request_access_context(request)
    return _conflict().check(case_id)
