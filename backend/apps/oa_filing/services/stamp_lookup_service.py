"""文件路径 → 合同反查服务。

根据本地文件路径，反查关联的合同和律所OA案件编号。
查询链路：文件路径 → CaseFolderBinding / ContractFolderBinding → Contract → law_firm_oa_case_number
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("apps.oa_filing.stamp_lookup")

# 最多向上查找的父目录层级
_MAX_PARENT_DEPTH = 6


@dataclass
class StampLookupResult:
    """反查结果。"""

    contract_id: int
    oa_case_number: str
    contract_name: str
    file_path: str


class StampLookupError(Exception):
    """文件路径反查失败。"""


class StampLookupService:  # pragma: no cover
    """文件路径 → 合同反查。"""

    @staticmethod
    def lookup_by_file_path(file_path: str) -> StampLookupResult:
        """根据文件路径反查合同，返回 OA 案件编号等信息。

        查询策略：
        1. 取文件所在目录
        2. 生成该目录的所有父路径（最多 6 级）
        3. 用 IN 查询 CaseFolderBinding（优先，更具体）
        4. 回退到 ContractFolderBinding
        5. 均未找到则抛出 StampLookupError
        """
        from apps.cases.models.material import CaseFolderBinding
        from apps.contracts.models.folder_binding import ContractFolderBinding

        file_dir = str(Path(file_path).parent)
        parents = [str(p) for p in Path(file_dir).parents[:_MAX_PARENT_DEPTH]]
        parents.append(file_dir)

        # 1. CaseFolderBinding（case 级别，更具体）
        case_binding = (
            CaseFolderBinding.objects.filter(folder_path__in=parents).select_related("case__contract").first()
        )
        if case_binding and case_binding.case and case_binding.case.contract:
            contract = case_binding.case.contract
            if contract.law_firm_oa_case_number:
                logger.info(
                    "CaseFolderBinding 命中: contract=%d, oa_no=%s",
                    contract.id,
                    contract.law_firm_oa_case_number,
                )
                return StampLookupResult(
                    contract_id=contract.id,
                    oa_case_number=contract.law_firm_oa_case_number,
                    contract_name=contract.name or "",
                    file_path=file_path,
                )

        # 2. ContractFolderBinding（contract 级别）
        contract_binding = (
            ContractFolderBinding.objects.filter(folder_path__in=parents).select_related("contract").first()
        )
        if contract_binding and contract_binding.contract:
            contract = contract_binding.contract
            if contract.law_firm_oa_case_number:
                logger.info(
                    "ContractFolderBinding 命中: contract=%d, oa_no=%s",
                    contract.id,
                    contract.law_firm_oa_case_number,
                )
                return StampLookupResult(
                    contract_id=contract.id,
                    oa_case_number=contract.law_firm_oa_case_number,
                    contract_name=contract.name or "",
                    file_path=file_path,
                )

        raise StampLookupError(f"无法根据文件路径找到关联合同: {file_path}")
