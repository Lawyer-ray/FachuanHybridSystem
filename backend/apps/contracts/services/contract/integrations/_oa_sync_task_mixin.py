"""同步任务执行（``ContractOASyncService`` 的 同步任务编排 / 异步核心 / 候选降级检索）。

从 ``contract_oa_sync_service.py`` 按子域拆出的 mixin，**方法体仍定义在宿主模块的语义下**：
本模块不持有任何业务名引用，一律经 ``self._host`` 回查 ``contract_oa_sync_service`` 的模块 globals。

.. important::
   在本文件里**禁止**直接写 ``Contract`` / ``ContractOASyncSession`` / ``timezone`` 等裸名——
   它们在本模块 globals 里不存在，会 ``NameError``；且测试 patch 的是**宿主模块的绑定位置**
   （``contract_oa_sync_service.Contract`` 等 7 处），只有经 ``self._host`` 回查才能命中。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from ._oa_service_contract import _OAServiceContract

if TYPE_CHECKING:
    from apps.oa_filing.services.oa_scripts.jtn.case_import import OAListCaseCandidate
from apps.contracts.models import Contract, ContractOASyncSession
from apps.oa_filing.services.oa_scripts.jtn.case_import import JtnCaseImportScript

logger = logging.getLogger(__name__)


class _OASyncTaskMixin(_OAServiceContract):
    """子域 mixin：具体方法见 ``contract_oa_sync_service.ContractOASyncService``。"""

    def run_sync_task(self, *, session_id: int) -> None:  # pragma: no cover
        session = self._host.ContractOASyncSession.objects.select_related("started_by").filter(id=session_id).first()
        if session is None:
            logger.warning("contract_oa_sync_session_missing", extra={"session_id": session_id})
            return

        if session.status in {self._host.ContractOASyncStatus.COMPLETED, self._host.ContractOASyncStatus.CANCELLED}:
            return

        try:
            credential = self._resolve_oa_credential(lawyer_id=session.started_by_id)
            contracts = list(self._build_missing_contract_queryset())
            total_count = len(contracts)

            logger.info(
                "contract_oa_sync_started",
                extra={
                    "session_id": session_id,
                    "total_count": total_count,
                    "started_by": session.started_by_id,
                    "credential_id": credential.id,
                },
            )

            self._update_session(
                session,
                status=self._host.ContractOASyncStatus.RUNNING,
                total_count=total_count,
                processed_count=0,
                matched_count=0,
                multiple_count=0,
                not_found_count=0,
                error_count=0,
                progress_message="正在连接金诚同达OA",  # privacy-allow OA 对接名
                error_message="",
                started_at=session.started_at or self._host.timezone.now(),
                result_payload={"items": [], "summary": {}, "remaining_contracts": []},
            )

            if total_count == 0:
                logger.info("contract_oa_sync_no_contracts", extra={"session_id": session_id})
                self._update_session(
                    session,
                    status=self._host.ContractOASyncStatus.COMPLETED,
                    progress_message="没有需要同步的合同",
                    completed_at=self._host.timezone.now(),
                    result_payload={"items": [], "summary": {}, "remaining_contracts": []},
                )
                return

            from apps.oa_filing.services.oa_scripts.jtn.case_import import JtnCaseImportScript

            final_payload = asyncio.run(
                self._run_sync_inner(
                    session=session,
                    credential=credential,
                    contracts=contracts,
                    total_count=total_count,
                )
            )

            self._update_session(
                session,
                status=self._host.ContractOASyncStatus.COMPLETED,
                completed_at=self._host.timezone.now(),
                progress_message="同步完成",
                result_payload=final_payload,
            )
        except Exception as exc:
            logger.exception("contract_oa_sync_failed", extra={"session_id": session_id})
            error_message = str(exc)
            sso_login_url = self._extract_sso_login_url(error_message)
            self._update_session(
                session,
                status=self._host.ContractOASyncStatus.FAILED,
                progress_message="同步失败",
                error_message=error_message,
                completed_at=self._host.timezone.now(),
                result_payload={
                    "items": [],
                    "summary": {},
                    "remaining_contracts": self.list_missing_oa_contracts(),
                    "sso_login_url": sso_login_url,
                },
            )

    async def _run_sync_inner(  # pragma: no cover
        self,
        *,
        session: ContractOASyncSession,
        credential: Any,
        contracts: list[Contract],
        total_count: int,
    ) -> dict[str, Any]:
        """异步核心逻辑：初始化脚本、遍历合同、关闭资源。"""
        from apps.oa_filing.services.oa_scripts.jtn.case_import import JtnCaseImportScript

        script = JtnCaseImportScript(
            account=credential.account,
            password=credential.password,
        )
        ensure_name_search_ready = getattr(script, "ensure_name_search_ready", None)
        if callable(ensure_name_search_ready):
            await ensure_name_search_ready()

        items: list[dict[str, Any]] = []
        matched_count = 0
        multiple_count = 0
        not_found_count = 0
        error_count = 0
        remaining_contracts_payload = self._serialize_missing_contracts(contracts)

        try:
            for index, contract in enumerate(contracts, start=1):
                contract_name = str(contract.name or "").strip()
                status = "not_found"
                message = ""
                candidates_payload: list[dict[str, str]] = []

                try:
                    if not contract_name:
                        status = "error"
                        error_count += 1
                        message = "合同名称为空，无法查询"
                    else:
                        candidates = await self._search_candidates_with_fallback_keywords(
                            script=script,
                            contract_id=int(contract.id),
                            contract_name=contract_name,
                            limit=6,
                        )
                        candidates_payload = [
                            {
                                "case_no": str(candidate.case_no),
                                "case_name": str(candidate.case_name),
                                "keyid": str(candidate.keyid),
                                "detail_url": str(candidate.detail_url),
                            }
                            for candidate in candidates
                        ]

                        if len(candidates) == 1:
                            status = "matched"
                            matched_count += 1
                            message = "已命中唯一候选，请人工确认后手动保存"
                        elif len(candidates) > 1:
                            status = "multiple"
                            multiple_count += 1
                            message = "命中多个结果，请人工确认"
                        else:
                            status = "not_found"
                            not_found_count += 1
                            message = "未找到匹配的OA案件"
                except Exception as exc:
                    logger.exception("contract_oa_sync_item_failed", extra={"contract_id": contract.id})
                    status = "error"
                    error_count += 1
                    message = str(exc)

                item = {
                    "contract_id": int(contract.id),
                    "contract_name": str(contract.name or ""),
                    "status": status,
                    "message": message,
                    "candidates": candidates_payload,
                }
                items.append(item)

                logger.info(
                    "contract_oa_sync_progress",
                    extra={
                        "session_id": session.id,
                        "current": index,
                        "total": total_count,
                        "contract_id": int(contract.id),
                        "contract_name": str(contract.name or ""),
                        "status": status,
                        "candidates_count": len(candidates_payload),
                    },
                )

                self._update_session(
                    session,
                    processed_count=index,
                    matched_count=matched_count,
                    multiple_count=multiple_count,
                    not_found_count=not_found_count,
                    error_count=error_count,
                    progress_message=str(
                        "正在同步 (%(current)s/%(total)s): %(name)s"
                        % {
                            "current": index,
                            "total": total_count,
                            "name": contract_name or "-",
                        }
                    ),
                    result_payload={
                        "items": items,
                        "summary": {
                            "matched_count": matched_count,
                            "multiple_count": multiple_count,
                            "not_found_count": not_found_count,
                            "error_count": error_count,
                        },
                        "remaining_contracts": remaining_contracts_payload,
                    },
                )
        finally:
            await script.close()

        logger.info(
            "contract_oa_sync_completed",
            extra={
                "session_id": session.id,
                "total_count": total_count,
                "matched_count": matched_count,
                "multiple_count": multiple_count,
                "not_found_count": not_found_count,
                "error_count": error_count,
            },
        )

        return {
            "items": items,
            "summary": {
                "matched_count": matched_count,
                "multiple_count": multiple_count,
                "not_found_count": not_found_count,
                "error_count": error_count,
            },
            "remaining_contracts": remaining_contracts_payload,
        }

    async def _search_candidates_with_fallback_keywords(
        self,
        *,
        script: JtnCaseImportScript,
        contract_id: int,
        contract_name: str,
        limit: int,
    ) -> list[OAListCaseCandidate]:  # pragma: no cover
        keywords = self._build_name_search_keywords(contract_name=contract_name, contract_id=contract_id)
        if not keywords:
            return []

        effective_limit = max(1, int(limit))
        expanded_limit = max(effective_limit * 5, 30)

        _SEARCH_TIMEOUT = 60  # 单次搜索超时秒数

        for keyword in keywords:
            try:
                candidates = await asyncio.wait_for(
                    script.search_cases_by_name(contract_name=keyword, limit=effective_limit),
                    timeout=_SEARCH_TIMEOUT,
                )
            except TimeoutError:
                logger.warning("contract_oa_sync_search_timeout contract_id=%s keyword=%s", contract_id, keyword)
                continue
            filtered_candidates = self._filter_candidates_by_contract_name(
                contract_name=contract_name,
                candidates=candidates,
            )
            sample_case_names = [str(item.case_name) for item in candidates[:3]]
            logger.info(
                "contract_oa_sync_name_search_attempt contract_id=%s keyword=%s candidate_count=%s filtered_candidate_count=%s sample_case_names=%s",
                contract_id,
                keyword,
                len(candidates),
                len(filtered_candidates),
                sample_case_names,
            )
            if filtered_candidates:
                return filtered_candidates[:effective_limit]

            if len(candidates) >= effective_limit:
                try:
                    expanded_candidates = await asyncio.wait_for(
                        script.search_cases_by_name(contract_name=keyword, limit=expanded_limit),
                        timeout=_SEARCH_TIMEOUT,
                    )
                except TimeoutError:
                    logger.warning(
                        "contract_oa_sync_expanded_search_timeout contract_id=%s keyword=%s", contract_id, keyword
                    )
                    continue
                expanded_filtered_candidates = self._filter_candidates_by_contract_name(
                    contract_name=contract_name,
                    candidates=expanded_candidates,
                )
                expanded_sample_case_names = [str(item.case_name) for item in expanded_candidates[:3]]
                logger.info(
                    "contract_oa_sync_name_search_expanded_attempt contract_id=%s keyword=%s candidate_count=%s filtered_candidate_count=%s sample_case_names=%s",
                    contract_id,
                    keyword,
                    len(expanded_candidates),
                    len(expanded_filtered_candidates),
                    expanded_sample_case_names,
                )
                if expanded_filtered_candidates:
                    return expanded_filtered_candidates[:effective_limit]

        return []
