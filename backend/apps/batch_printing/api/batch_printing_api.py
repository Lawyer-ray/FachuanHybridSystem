from __future__ import annotations

from uuid import UUID

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
def get_capabilities(request: HttpRequest) -> CapabilityOut:
    payload = get_file_prepare_service().get_capability_snapshot()
    return CapabilityOut(**payload)


@router.get("/presets", response=list[PrintPresetSnapshotOut])
def list_presets(
    request: HttpRequest,
    printer_name: str | None = None,
    keyword: str | None = None,
) -> list[PrintPresetSnapshotOut]:
    service = get_preset_service()
    presets = service.list_presets(printer_name=printer_name or "", keyword=keyword or "")
    return [PrintPresetSnapshotOut(**service.build_preset_payload(preset=item)) for item in presets]


@router.get("/presets/{preset_id}", response=PrintPresetSnapshotOut)
def get_preset(request: HttpRequest, preset_id: int) -> PrintPresetSnapshotOut:
    service = get_preset_service()
    preset = service.get_preset(preset_id=preset_id)
    return PrintPresetSnapshotOut(**service.build_preset_payload(preset=preset))


@router.post("/presets/sync", response=PresetSyncOut)
def sync_presets(request: HttpRequest) -> PresetSyncOut:
    payload = get_preset_discovery_service().sync_presets()
    return PresetSyncOut(**payload)


@router.get("/rules", response=list[PrintKeywordRuleOut])
def list_rules(
    request: HttpRequest,
    enabled: bool | None = None,
    keyword: str | None = None,
    printer_name: str | None = None,
    preset_snapshot_id: int | None = None,
) -> list[PrintKeywordRuleOut]:
    service = get_rule_service()
    rules = service.list_rules(
        enabled=enabled,
        keyword=keyword or "",
        printer_name=printer_name or "",
        preset_snapshot_id=preset_snapshot_id,
    )
    return [PrintKeywordRuleOut(**service.build_rule_payload(rule=item)) for item in rules]


@router.post("/rules", response=PrintKeywordRuleOut)
def create_rule(request: HttpRequest, payload: PrintKeywordRuleIn) -> PrintKeywordRuleOut:
    service = get_rule_service()
    rule = service.create_rule(payload=payload.model_dump())
    return PrintKeywordRuleOut(**service.build_rule_payload(rule=rule))


@router.get("/rules/{rule_id}", response=PrintKeywordRuleOut)
def get_rule(request: HttpRequest, rule_id: int) -> PrintKeywordRuleOut:
    service = get_rule_service()
    rule = service.get_rule(rule_id=rule_id)
    return PrintKeywordRuleOut(**service.build_rule_payload(rule=rule))


@router.put("/rules/{rule_id}", response=PrintKeywordRuleOut)
def update_rule(request: HttpRequest, rule_id: int, payload: PrintKeywordRuleUpdateIn) -> PrintKeywordRuleOut:
    service = get_rule_service()
    rule = service.update_rule(rule_id=rule_id, payload=payload.model_dump(exclude_unset=True))
    return PrintKeywordRuleOut(**service.build_rule_payload(rule=rule))


@router.delete("/rules/{rule_id}")
def delete_rule(request: HttpRequest, rule_id: int) -> dict[str, bool]:
    get_rule_service().delete_rule(rule_id=rule_id)
    return {"success": True}


@router.get("/jobs", response=list[BatchPrintJobSummaryOut])
def list_batch_print_jobs(
    request: HttpRequest,
    status: str | None = None,
    keyword: str | None = None,
) -> list[BatchPrintJobSummaryOut]:
    service = get_batch_print_job_service()
    jobs = service.list_jobs(status=status or "", keyword=keyword or "")
    return [BatchPrintJobSummaryOut(**service.build_job_summary_payload(job=item)) for item in jobs]


@router.post("/jobs", response=BatchPrintSubmitOut)
def create_batch_print_job(request: HttpRequest) -> BatchPrintSubmitOut:
    files = list(request.FILES.getlist("files"))
    job = get_batch_print_job_service().create_job(files=files, created_by=getattr(request, "user", None))
    return BatchPrintSubmitOut(job_id=str(job.id), status=job.status)


@router.get("/jobs/{job_id}", response=BatchPrintJobOut)
def get_batch_print_job(request: HttpRequest, job_id: UUID) -> BatchPrintJobOut:
    service = get_batch_print_job_service()
    job = service.get_job(job_id)
    payload = service.build_job_payload(job=job)
    return BatchPrintJobOut(**payload)


@router.post("/jobs/{job_id}/cancel", response=BatchPrintSubmitOut)
def cancel_batch_print_job(request: HttpRequest, job_id: UUID) -> BatchPrintSubmitOut:
    job = get_batch_print_job_service().request_cancel(job_id=job_id)
    return BatchPrintSubmitOut(job_id=str(job.id), status=job.status)


@router.delete("/jobs/{job_id}")
def delete_batch_print_job(request: HttpRequest, job_id: UUID) -> dict[str, bool]:
    get_batch_print_job_service().delete_job(job_id=job_id)
    return {"success": True}
