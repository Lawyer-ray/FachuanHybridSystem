"""OA 字段回填与凭据（``ContractOASyncService`` 的 手工字段保存 / 字段回填 / OA 凭据解析 / SSO 链接提取）。

从 ``contract_oa_sync_service.py`` 按子域拆出的 mixin，**方法体仍定义在宿主模块的语义下**：
本模块不持有任何业务名引用，一律经 ``self._host`` 回查 ``contract_oa_sync_service`` 的模块 globals。

.. important::
   在本文件里**禁止**直接写 ``Contract`` / ``ContractOASyncSession`` / ``timezone`` 等裸名——
   它们在本模块 globals 里不存在，会 ``NameError``；且测试 patch 的是**宿主模块的绑定位置**
   （``contract_oa_sync_service.Contract`` 等 7 处），只有经 ``self._host`` 回查才能命中。
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Q

from ._oa_service_contract import _OAServiceContract

if TYPE_CHECKING:
    from apps.oa_filing.services.oa_scripts.jtn.case_import import OAListCaseCandidate
from apps.contracts.models import Contract
from apps.organization.models import AccountCredential

logger = logging.getLogger(__name__)


class _OAFieldMixin(_OAServiceContract):
    """子域 mixin：具体方法见 ``contract_oa_sync_service.ContractOASyncService``。"""

    def save_manual_contract_oa_fields(self, *, updates: list[dict[str, Any]]) -> dict[str, Any]:  # pragma: no cover
        """手动保存合同 OA 字段。"""
        updated_count = 0
        errors: list[dict[str, str]] = []
        validate_url = URLValidator()

        # 收集所有需要更新的对象，最后用 bulk_update 批量写入
        contracts_to_update: list[dict[str, Any]] = []
        contract_ids: list[int] = []

        for row in updates:
            contract_id_raw = row.get("id", row.get("contract_id"))
            try:
                contract_id = int(str(contract_id_raw)) if contract_id_raw is not None else 0
            except (TypeError, ValueError):
                errors.append({"contract_id": str(contract_id_raw or ""), "message": "合同ID无效"})
                continue

            case_number = str(row.get("law_firm_oa_case_number") or "").strip()
            oa_url = str(row.get("law_firm_oa_url") or "").strip()

            if oa_url:
                try:
                    validate_url(oa_url)
                except ValidationError:
                    errors.append({"contract_id": str(contract_id), "message": "律所OA链接格式无效"})
                    continue

            contract_ids.append(contract_id)
            # 暂存待更新的字段值，在 bulk 查询后再赋值
            contracts_to_update.append(
                # 占位，稍后用真实对象替换；这里先保存元信息
                {"_id": contract_id, "case_number": case_number or None, "oa_url": oa_url or ""}
            )

        if contracts_to_update:
            # 批量查询所有涉及的合同
            id_set = {item["_id"] for item in contracts_to_update}
            contract_map = {c.id: c for c in self._host.Contract.objects.filter(id__in=id_set)}
            found_ids: set[int] = set()

            for item in contracts_to_update:
                cid = item["_id"]
                contract_obj = contract_map.get(cid)
                if contract_obj is None:
                    errors.append({"contract_id": str(cid), "message": "合同不存在"})
                    continue
                contract_obj.law_firm_oa_case_number = item["case_number"]
                contract_obj.law_firm_oa_url = item["oa_url"]
                found_ids.add(cid)
                updated_count += 1

            # 批量更新（仅更新有变更的字段）
            if found_ids:
                objs_to_update = [contract_map[cid] for cid in found_ids]
                with transaction.atomic():
                    self._host.Contract.objects.bulk_update(
                        objs_to_update,
                        ["law_firm_oa_case_number", "law_firm_oa_url"],
                    )

        return {
            "updated_count": updated_count,
            "error_count": len(errors),
            "errors": errors,
            "remaining_contracts": self.list_missing_oa_contracts(),
        }

    def _fill_contract_oa_fields(
        self, *, contract: Contract, candidate: OAListCaseCandidate
    ) -> None:  # pragma: no cover
        case_no = str(candidate.case_no).strip() if candidate.case_no else ""
        detail_url = str(candidate.detail_url).strip() if candidate.detail_url else ""
        with transaction.atomic():
            self._host.Contract.objects.filter(id=contract.id).update(
                law_firm_oa_case_number=case_no or None,
                law_firm_oa_url=detail_url or "",
            )

    def _resolve_oa_credential(self, *, lawyer_id: int | None) -> AccountCredential:
        from apps.organization.models import AccountCredential

        if lawyer_id is None:
            raise RuntimeError("当前用户无效，无法获取OA凭证")

        credential = (
            AccountCredential.objects.filter(
                Q(account__icontains="jtn.com") | Q(url__icontains="jtn.com"),
                lawyer_id=lawyer_id,
            )
            .order_by("-last_login_success_at", "-id")
            .first()
        )
        if credential is None:
            raise RuntimeError("未找到金诚同达OA账号，请先在账号密码中配置")  # privacy-allow OA 对接名
        return credential

    def _extract_sso_login_url(self, text: str) -> str:
        message = str(text or "")
        if "access.jtn.com" not in message:
            return ""
        url_match = re.search(r"https://access\.jtn\.com/[^\s\"'<>]+", message)
        if url_match:
            return str(url_match.group(0)).strip()
        return "https://access.jtn.com/login"
