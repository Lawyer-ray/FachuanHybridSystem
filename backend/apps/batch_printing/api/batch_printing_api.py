from __future__ import annotations

from uuid import UUID

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.batch_printing.schemas import (
    BatchPrintJobOut,
    BatchPrintJobSummaryOut,
    BatchPrintSubmitOut,
    CapabilityOut,
    PresetSyncOut,
    PrintKeywordRuleIn,
    PrintKeywordRuleOut,
    PrintKeywordRuleUpdateIn,
    PrintPresetSnapshotOut,
)
from apps.batch_printing.services.wiring import (
    get_batch_print_job_service,
    get_file_prepare_service,
    get_preset_discovery_service,
    get_preset_service,
    get_rule_service,
)

router = Router(tags=["批量打印"])


@router.get("/capabilities", response=CapabilityOut)
async def get_capabilities(request: HttpRequest) -> CapabilityOut:  # pragma: no cover
    payload = await sync_to_async(get_file_prepare_service().get_capability_snapshot)()
    return CapabilityOut(**payload)


@router.get("/presets", response=list[PrintPresetSnapshotOut])
async def list_presets(  # pragma: no cover
    request: HttpRequest,
    printer_name: str | None = None,
    keyword: str | None = None,
) -> list[PrintPresetSnapshotOut]:
    service = get_preset_service()
    presets = await sync_to_async(service.list_presets)(printer_name=printer_name or "", keyword=keyword or "")
    return [PrintPresetSnapshotOut(**service.build_preset_payload(preset=item)) for item in presets]


@router.get("/presets/{preset_id}", response=PrintPresetSnapshotOut)
async def get_preset(request: HttpRequest, preset_id: int) -> PrintPresetSnapshotOut:  # pragma: no cover
    service = get_preset_service()
    preset = await sync_to_async(service.get_preset)(preset_id=preset_id)
    return PrintPresetSnapshotOut(**service.build_preset_payload(preset=preset))


@router.post("/presets/sync", response=PresetSyncOut)
async def sync_presets(request: HttpRequest) -> PresetSyncOut:  # pragma: no cover
    payload = await sync_to_async(get_preset_discovery_service().sync_presets)()
    return PresetSyncOut(**payload)


@router.get("/rules", response=list[PrintKeywordRuleOut])
async def list_rules(  # pragma: no cover
    request: HttpRequest,
    enabled: bool | None = None,
    keyword: str | None = None,
    printer_name: str | None = None,
    preset_snapshot_id: int | None = None,
) -> list[PrintKeywordRuleOut]:
    service = get_rule_service()
    rules = await sync_to_async(service.list_rules)(
        enabled=enabled,
        keyword=keyword or "",
        printer_name=printer_name or "",
        preset_snapshot_id=preset_snapshot_id,
    )
    return [PrintKeywordRuleOut(**service.build_rule_payload(rule=item)) for item in rules]


@router.post("/rules", response=PrintKeywordRuleOut)
async def create_rule(request: HttpRequest, payload: PrintKeywordRuleIn) -> PrintKeywordRuleOut:  # pragma: no cover
    service = get_rule_service()
    rule = await sync_to_async(service.create_rule)(payload=payload.model_dump())
    return PrintKeywordRuleOut(**service.build_rule_payload(rule=rule))


@router.get("/rules/{rule_id}", response=PrintKeywordRuleOut)
async def get_rule(request: HttpRequest, rule_id: int) -> PrintKeywordRuleOut:  # pragma: no cover
    service = get_rule_service()
    rule = await sync_to_async(service.get_rule)(rule_id=rule_id)
    return PrintKeywordRuleOut(**service.build_rule_payload(rule=rule))


@router.put("/rules/{rule_id}", response=PrintKeywordRuleOut)
async def update_rule(request: HttpRequest, rule_id: int, payload: PrintKeywordRuleUpdateIn) -> PrintKeywordRuleOut:  # pragma: no cover
    service = get_rule_service()
    rule = await sync_to_async(service.update_rule)(rule_id=rule_id, payload=payload.model_dump(exclude_unset=True))
    return PrintKeywordRuleOut(**service.build_rule_payload(rule=rule))


@router.delete("/rules/{rule_id}")
async def delete_rule(request: HttpRequest, rule_id: int) -> dict[str, bool]:  # pragma: no cover
    await sync_to_async(get_rule_service().delete_rule)(rule_id=rule_id)
    return {"success": True}


@router.get("/jobs", response=list[BatchPrintJobSummaryOut])
async def list_batch_print_jobs(  # pragma: no cover
    request: HttpRequest,
    status: str | None = None,
    keyword: str | None = None,
) -> list[BatchPrintJobSummaryOut]:
    service = get_batch_print_job_service()
    jobs = await sync_to_async(service.list_jobs)(status=status or "", keyword=keyword or "")
    return [BatchPrintJobSummaryOut(**service.build_job_summary_payload(job=item)) for item in jobs]


@router.post("/jobs", response=BatchPrintSubmitOut)
async def create_batch_print_job(request: HttpRequest) -> BatchPrintSubmitOut:  # pragma: no cover
    files = list(request.FILES.getlist("files"))
    job = await sync_to_async(get_batch_print_job_service().create_job)(files=files, created_by=getattr(request, "user", None))
    return BatchPrintSubmitOut(job_id=str(job.id), status=job.status)


@router.get("/jobs/{job_id}", response=BatchPrintJobOut)
async def get_batch_print_job(request: HttpRequest, job_id: UUID) -> BatchPrintJobOut:  # pragma: no cover
    service = get_batch_print_job_service()
    job = await sync_to_async(service.get_job)(job_id)
    payload = service.build_job_payload(job=job)
    return BatchPrintJobOut(**payload)


@router.post("/jobs/{job_id}/cancel", response=BatchPrintSubmitOut)
async def cancel_batch_print_job(request: HttpRequest, job_id: UUID) -> BatchPrintSubmitOut:  # pragma: no cover
    job = await sync_to_async(get_batch_print_job_service().request_cancel)(job_id=job_id)
    return BatchPrintSubmitOut(job_id=str(job.id), status=job.status)


@router.delete("/jobs/{job_id}")
async def delete_batch_print_job(request: HttpRequest, job_id: UUID) -> dict[str, bool]:  # pragma: no cover
    await sync_to_async(get_batch_print_job_service().delete_job)(job_id=job_id)
    return {"success": True}
