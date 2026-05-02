from __future__ import annotations

from .execution import MacPrintExecutorService, RuleService
from .job import BatchPrintJobService, FilePrepareService
from .preset import PresetDiscoveryService, PrintPresetSnapshotService


def get_preset_discovery_service() -> PresetDiscoveryService:
    return PresetDiscoveryService()


def get_preset_service() -> PrintPresetSnapshotService:
    return PrintPresetSnapshotService()


def get_rule_service() -> RuleService:
    return RuleService()


def get_file_prepare_service() -> FilePrepareService:
    return FilePrepareService()


def get_mac_print_executor_service() -> MacPrintExecutorService:
    return MacPrintExecutorService()


def get_batch_print_job_service() -> BatchPrintJobService:
    return BatchPrintJobService(
        rule_service=get_rule_service(),
        preset_discovery_service=get_preset_discovery_service(),
        file_prepare_service=get_file_prepare_service(),
        print_executor_service=get_mac_print_executor_service(),
    )
