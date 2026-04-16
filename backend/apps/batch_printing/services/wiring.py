from __future__ import annotations

from .file_prepare_service import FilePrepareService
from .job_service import BatchPrintJobService
from .mac_print_executor_service import MacPrintExecutorService
from .preset_discovery_service import PresetDiscoveryService
from .preset_service import PrintPresetSnapshotService
from .rule_service import RuleService


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
