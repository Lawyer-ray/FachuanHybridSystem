"""案件导出场景下的合同序列化桥接。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

_CASE_ADMIN_CONTRACT_EXPORT_PREFETCHES: tuple[str, ...] = (
    "contract__contract_parties__client__identity_docs",
    "contract__contract_parties__client__property_clues__attachments",
    "contract__assignments__lawyer",
    "contract__finalized_materials",
    "contract__supplementary_agreements__parties__client",
    "contract__payments__invoices",
    "contract__finance_logs__actor",
    "contract__client_payment_records",
)

_CASE_ADMIN_CONTRACT_FILE_PREFETCHES: tuple[str, ...] = (
    "contract__finalized_materials",
    "contract__contract_parties__client__identity_docs",
    "contract__contract_parties__client__property_clues__attachments",
)

if TYPE_CHECKING:
    from apps.contracts.models import Contract


def get_case_admin_contract_export_prefetches() -> tuple[str, ...]:
    """返回 CaseAdmin 导出合同时需要的 prefetch 路径。"""
    return _CASE_ADMIN_CONTRACT_EXPORT_PREFETCHES


def get_case_admin_contract_file_prefetches() -> tuple[str, ...]:
    """返回 CaseAdmin 收集合同文件路径时需要的 prefetch 路径。"""
    return _CASE_ADMIN_CONTRACT_FILE_PREFETCHES


def serialize_contract_for_case_export(contract: Contract) -> dict[str, object]:
    """在 Case 导出场景中序列化关联合同。"""
    from apps.cases.services.case.case_export_serializer_service import serialize_case_obj
    from apps.contracts.services.contract.contract_export_serializer_service import serialize_contract_obj

    return serialize_contract_obj(contract, case_serializer=serialize_case_obj)


def collect_contract_file_paths_for_case_export(
    contract: Contract,
    add_path: Callable[[str], None],
) -> None:
    """收集合同及其当事人相关文件路径。"""
    for material in contract.finalized_materials.all():
        add_path(material.file_path)

    for party in contract.contract_parties.all():
        for identity_doc in party.client.identity_docs.all():
            add_path(identity_doc.file_path)
        for clue in party.client.property_clues.all():
            for attachment in clue.attachments.all():
                add_path(attachment.file_path)
