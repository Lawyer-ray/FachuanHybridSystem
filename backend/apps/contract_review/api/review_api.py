import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from asgiref.sync import sync_to_async
from django.http import FileResponse, HttpRequest, HttpResponse
from ninja import File, Form, Router
from ninja.files import UploadedFile

from apps.contract_review.schemas.review_schemas import (
    ConfirmPartyIn,
    ContentVersionOut,
    ResolveRevisionIn,
    ResolveRevisionOut,
    RevisionListOut,
    TaskCreatedOut,
    TaskStatusOut,
    VersionChainOut,
)
from apps.core.infrastructure.throttling import rate_limit_from_settings

logger = logging.getLogger(__name__)
router = Router()


def _get_review_service() -> Any:  # pragma: no cover
    from apps.contract_review.services.wiring import get_review_service

    return get_review_service()


def _get_model_list_service() -> Any:  # pragma: no cover
    from apps.core.llm.model_list_service import ModelListService

    return ModelListService()


def _check_task_access(task: Any, user: Any) -> bool:  # pragma: no cover
    """检查用户是否有权限访问任务"""
    if user is None:
        return False
    # 超级用户可以访问所有任务
    if user.is_superuser:
        return True
    # 普通用户只能访问自己的任务
    return bool(task.user_id == user.id)


@router.post("/upload", response=TaskCreatedOut)
@rate_limit_from_settings("TASK", by_user=True)
async def upload_contract(  # pragma: no cover
    request: HttpRequest,
    file: UploadedFile = File(...),
    model_name: str = Form(""),
) -> dict[str, Any] | HttpResponse:
    svc = _get_review_service()
    # thread_sensitive=True（与其他异步 API 一致）：upload_contract 是同步阻塞的
    # 数据库写入，必须回到调用线程执行。用 False 会丢到 worker 线程，写操作既
    # 看不到请求所在事务的未提交数据（生产表现为外键找不到当前用户），
    # 也在测试的 transaction.atomic 之外污染库。
    task = await sync_to_async(svc.upload_contract, thread_sensitive=True)(file, request.user, model_name=model_name)
    parties: dict[str, str] = {}
    for key in ("party_a", "party_b", "party_c", "party_d"):
        val = getattr(task, key, "")
        if val:
            parties[key] = val
    return {
        "task_id": task.id,
        "status": task.status,
        "contract_title": task.contract_title or None,
        "parties": parties,
    }


@router.post("/{task_id}/confirm-party", response=TaskStatusOut)
def confirm_party(  # pragma: no cover
    request: HttpRequest,
    task_id: UUID,
    payload: ConfirmPartyIn,
) -> dict[str, Any] | HttpResponse:
    svc = _get_review_service()
    # 权限检查
    task = svc.get_task_status(task_id)
    if not _check_task_access(task, request.user):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("无权操作此任务")
    # 收集用户手动修正的当事人名称（仅传递非空值）
    party_overrides: dict[str, str] = {}
    for key in ("party_a", "party_b", "party_c", "party_d"):
        val = getattr(payload, key, "")
        if val.strip():
            party_overrides[key] = val.strip()
    task = svc.confirm_party(
        task_id,
        payload.represented_party,
        request.user,
        payload.reviewer_name,
        payload.selected_steps,
        party_overrides or None,
        client_note=payload.client_note,
        client_demands=payload.client_demands,
        our_client_name=payload.our_client_name,
        stance_basis=payload.stance_basis,
    )
    return {
        "task_id": task.id,
        "status": task.status,
        "current_step": task.current_step or None,
        "error_message": task.error_message or None,
        "output_filename": None,
    }


@router.get("/{task_id}/status", response=TaskStatusOut)
def get_task_status(request: HttpRequest, task_id: UUID) -> dict[str, Any] | HttpResponse:  # pragma: no cover
    svc = _get_review_service()
    task = svc.get_task_status(task_id)
    if not _check_task_access(task, request.user):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("无权访问此任务")
    output_filename = Path(task.output_file).name if task.output_file else None
    return {
        "task_id": task.id,
        "status": task.status,
        "current_step": task.current_step or None,
        "error_message": task.error_message or None,
        "output_filename": output_filename,
    }


@router.get("/{task_id}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_result(request: HttpRequest, task_id: UUID) -> FileResponse | HttpResponse:  # pragma: no cover
    svc = _get_review_service()
    # 权限检查
    task = svc.get_task_status(task_id)
    if not _check_task_access(task, request.user):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("无权下载此文件")
    path = svc.get_result_file(task_id)
    return FileResponse(path.open("rb"), as_attachment=True, filename=path.name)


@router.get("/{task_id}/download-original")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_original(request: HttpRequest, task_id: UUID) -> FileResponse | HttpResponse:  # pragma: no cover
    svc = _get_review_service()
    # 权限检查
    task = svc.get_task_status(task_id)
    if not _check_task_access(task, request.user):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("无权下载此文件")
    path = svc.get_original_file(task_id)
    return FileResponse(path.open("rb"), as_attachment=True, filename=path.name)


@router.get("/{task_id}/revisions", response=RevisionListOut)
def list_revisions(request: HttpRequest, task_id: UUID) -> Any:  # pragma: no cover
    """取某次审查的结构化修订清单（复审台左栏）。

    为什么不是直接读 docx 的 Track Changes：痕迹里没有等级、依据、驳回理由，
    也没有「律师已决策」这个状态。清单是决策载体，docx 是产物。

    ORM 查询在 service 层（结构门禁：API 层不得直连 ORM）。
    """
    svc = _get_review_service()
    task = svc.get_task_or_none(task_id)
    if task is None:
        from apps.core.exceptions import NotFoundError

        raise NotFoundError("审查任务不存在")
    if not _check_task_access(task, request.user):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("无权访问此任务")
    return svc.list_revisions(task_id)


@router.post("/{task_id}/revisions/{revision_id}/resolve", response=ResolveRevisionOut)
@rate_limit_from_settings("TASK", by_user=True)
def resolve_revision(
    request: HttpRequest, task_id: UUID, revision_id: UUID, payload: ResolveRevisionIn
) -> Any:  # pragma: no cover
    """律师对单条建议做决策（采纳 / 驳回 / 撤销）。

    **只改状态，不改文档**：采纳后文档侧的修订痕迹由 OnlyOffice 编辑器写入
    （前端驱动）。后端不碰 docx 产物——同一份产物可能同时被编辑器持有，
    两边都写会互相覆盖。
    """
    svc = _get_review_service()
    task = svc.get_task_or_none(task_id)
    if task is None:
        from apps.core.exceptions import NotFoundError

        raise NotFoundError("审查任务不存在")
    if not _check_task_access(task, request.user):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("无权访问此任务")
    return svc.resolve_revision(task_id, revision_id, payload.action, payload.reason or "")


@router.get("/{task_id}/content-version", response=ContentVersionOut)
def get_content_version(request: HttpRequest, task_id: UUID) -> Any:  # pragma: no cover
    """文档内容版本：告诉复审台「画布该不该重载」。

    旧做法是前端自己拼 `version = taskId:acceptedCount`，采纳一次就变 →
    整篇重建 DS 画布（5–15 秒）。律师逐条过一份 30 处建议的合同时，
    每点一次采纳都在等重载。
    """
    svc = _get_review_service()
    task = svc.get_task_or_none(task_id)
    if task is None:
        return {"content_version": "", "saved_version": 0, "output_file": ""}
    if not _check_task_access(task, request.user):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("无权访问此任务")
    return svc.get_content_version(task_id)


@router.get("/{task_id}/versions", response=VersionChainOut)
def get_versions(request: HttpRequest, task_id: UUID) -> Any:  # pragma: no cover
    """文档版本链：从客户来稿 → AI 修订版 → 律师编辑版（→ 客户回稿）。

    以前版本信息只活在文件名（`[修订版]V1_日期`）：改个名就断链，
    排序也只对同一天有效。这里把它变成真实关系（parent 指向改自的那版）。
    """
    from apps.contract_review.services.review.version_chain import list_versions
    from apps.core.exceptions import NotFoundError

    svc = _get_review_service()
    task = svc.get_task_or_none(task_id)
    if task is None:
        raise NotFoundError("审查任务不存在")
    if not _check_task_access(task, request.user):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("无权访问此任务")

    items = list_versions(task_id)
    return {"task_id": task_id, "total": len(items), "items": items}


@router.get("/models")
async def get_models(request: HttpRequest) -> dict[str, Any]:  # pragma: no cover
    svc = _get_model_list_service()
    result = await sync_to_async(svc.get_result, thread_sensitive=False)()
    return {
        "models": result.models,
        "is_fallback": result.is_fallback,
        "error_message": result.error_message,
    }
