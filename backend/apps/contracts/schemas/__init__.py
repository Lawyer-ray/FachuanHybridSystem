"""合同 Schemas 包 — 统一导出所有 Schema。"""

from __future__ import annotations

from apps.core.api.schemas_shared import ReminderLiteOut as ReminderOut

# Client Schemas
from .client_schemas import ClientIdentityDocOut, ClientOut

# Contract Core Schemas
from .contract_schemas import (
    ClientPaymentRecordOut,
    ContractAssignmentOut,
    ContractIn,
    ContractOut,
    ContractPaginatedOut,
    ContractUpdate,
    FinalizedMaterialOut,
    UpdateLawyersIn,
)

# Folder Binding Schemas
from .folder_binding_schemas import (
    ContractStorageSubdirRecommendResponseSchema,
    ContractStorageSubdirBrowseResponseSchema,
    ContractStorageSubdirEntrySchema,
    FolderBindingCreateSchema,
    FolderBindingResponseSchema,
    FolderBrowseEntrySchema,
    FolderBrowseResponseSchema,
)
from .folder_scan_schemas import (
    ArchiveItemOptionOut,
    ContractFolderScanCandidateOut,
    ContractFolderScanConfirmIn,
    ContractFolderScanConfirmItemIn,
    ContractFolderScanConfirmOut,
    ContractFolderScanStartIn,
    ContractFolderScanStartOut,
    ContractFolderScanStatusOut,
    ContractFolderScanSubfolderListOut,
    ContractFolderScanSubfolderOptionOut,
    ContractFolderScanSummaryOut,
    WorkLogSuggestionOut,
)

# Lawyer, Reminder, Case Schemas
from .lawyer_schemas import CaseOut, LawyerOut

# Party Schemas
from .party_schemas import ContractPartyIn, ContractPartyOut, ContractPartySourceOut

# Payment Schemas
from .payment_schemas import (
    ContractPaymentIn,
    ContractPaymentOut,
    ContractPaymentUpdate,
    FinanceStatsItem,
    FinanceStatsOut,
)

# Supplementary Agreement Schemas
from .supplementary_schemas import (
    SupplementaryAgreementIn,
    SupplementaryAgreementInput,
    SupplementaryAgreementOut,
    SupplementaryAgreementPartyIn,
    SupplementaryAgreementPartyInput,
    SupplementaryAgreementPartyOut,
    SupplementaryAgreementUpdate,
)

__all__ = [
    # Client
    "ClientIdentityDocOut",
    "ClientOut",
    # Lawyer, Reminder, Case
    "LawyerOut",
    "ReminderOut",
    "CaseOut",
    # Party
    "ContractPartyIn",
    "ContractPartyOut",
    "ContractPartySourceOut",
    # Payment
    "ContractPaymentIn",
    "ContractPaymentOut",
    "ContractPaymentUpdate",
    "FinanceStatsItem",
    "FinanceStatsOut",
    # Supplementary Agreement
    "SupplementaryAgreementPartyInput",
    "SupplementaryAgreementInput",
    "SupplementaryAgreementIn",
    "SupplementaryAgreementUpdate",
    "SupplementaryAgreementPartyIn",
    "SupplementaryAgreementPartyOut",
    "SupplementaryAgreementOut",
    # Folder Binding
    "FolderBindingCreateSchema",
    "FolderBindingResponseSchema",
    "FolderBrowseEntrySchema",
    "FolderBrowseResponseSchema",
    "ContractStorageSubdirEntrySchema",
    "ContractStorageSubdirBrowseResponseSchema",
    "ContractStorageSubdirRecommendResponseSchema",
    # Folder Scan
    "ContractFolderScanStartIn",
    "ContractFolderScanStartOut",
    "ContractFolderScanSubfolderOptionOut",
    "ContractFolderScanSubfolderListOut",
    "ContractFolderScanSummaryOut",
    "ContractFolderScanCandidateOut",
    "ContractFolderScanStatusOut",
    "ContractFolderScanConfirmItemIn",
    "ContractFolderScanConfirmIn",
    "ContractFolderScanConfirmOut",
    # Contract Core
    "UpdateLawyersIn",
    "ContractIn",
    "ContractAssignmentOut",
    "ContractOut",
    "ContractPaginatedOut",
    "ContractUpdate",
]
