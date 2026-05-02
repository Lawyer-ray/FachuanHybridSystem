"""合同 OA 信息同步服务。"""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import Contract, ContractOASyncSession, ContractOASyncStatus, ContractParty
from apps.core.dependencies.core import build_task_submission_service

if TYPE_CHECKING:
    from apps.oa_filing.services.oa_scripts.jtn_case_import import JtnCaseImportScript, OAListCaseCandidate
    from apps.organization.models import AccountCredential

logger = logging.getLogger(__name__)


class ContractOASyncService:
    """合同 OA 链接与 OA 案件编号同步服务。"""

    _ACTIVE_STATUSES = {ContractOASyncStatus.PENDING, ContractOASyncStatus.RUNNING}
    _STALE_RUNNING_MINUTES = 3

    def list_missing_oa_contracts(self) -> list[dict[str, Any]]:
        """列出缺少 OA 关键信息的合同。"""
        contracts = list(self._build_missing_contract_queryset())
        return self._serialize_missing_contracts(contracts)

    def create_or_get_active_session(self, *, started_by: Any | None) -> ContractOASyncSession:
        """创建或复用进行中的会话。"""
        existing = (
            ContractOASyncSession.objects.filter(status__in=self._ACTIVE_STATUSES).order_by("-created_at").first()
        )
        if existing is not None:
            if self._is_stale_active_session(existing):
                logger.warning(
                    "contract_oa_sync_stale_session_detected",
                    extra={"session_id": existing.id, "status": existing.status},
                )
                self._update_session(
                    existing,
                    status=ContractOASyncStatus.FAILED,
                    progress_message=str(_("检测到陈旧会话，已重置")),
                    error_message=str(_("上一次同步任务异常中断，请重新发起")),
                    completed_at=timezone.now(),
                )
            else:
                return existing

        started_by_user = started_by if getattr(started_by, "is_authenticated", False) else None
        return ContractOASyncSession.objects.create(
            status=ContractOASyncStatus.PENDING,
            progress_message=str(_("等待启动")),
            started_by=started_by_user,
        )

    def submit_session_task(self, *, session: ContractOASyncSession) -> ContractOASyncSession:
        """提交会话异步任务。"""
        if session.status == ContractOASyncStatus.RUNNING and session.task_id:
            return session

        task_id = build_task_submission_service().submit(
            "apps.contracts.services.contract.integrations.contract_oa_sync_service.run_contract_oa_sync_task",
            args=[int(session.id)],
            task_name=f"contract_oa_sync_{session.id}",
        )
        ContractOASyncSession.objects.filter(id=session.id).update(
            status=ContractOASyncStatus.PENDING,
            task_id=str(task_id),
            progress_message=str(_("同步任务已入队，等待执行")),
            error_message="",
            updated_at=timezone.now(),
        )
        session.refresh_from_db()
        return session

    def get_session(self, *, session_id: int) -> ContractOASyncSession | None:
        return ContractOASyncSession.objects.filter(id=session_id).first()

    def build_status_payload(self, *, session: ContractOASyncSession) -> dict[str, Any]:
        payload = dict(session.result_payload or {})
        summary = payload.get("summary") or {}
        error_message = str(session.error_message or "")
        sso_login_url = str(payload.get("sso_login_url") or "").strip() or self._extract_sso_login_url(error_message)
        return {
            "session_id": int(session.id),
            "status": session.status,
            "progress_message": str(session.progress_message or ""),
            "total_count": int(session.total_count or 0),
            "processed_count": int(session.processed_count or 0),
            "matched_count": int(session.matched_count or 0),
            "multiple_count": int(session.multiple_count or 0),
            "not_found_count": int(session.not_found_count or 0),
            "error_count": int(session.error_count or 0),
            "error_message": error_message,
            "sso_login_url": sso_login_url,
            "summary": {
                "matched_count": int(summary.get("matched_count", 0) or 0),
                "multiple_count": int(summary.get("multiple_count", 0) or 0),
                "not_found_count": int(summary.get("not_found_count", 0) or 0),
                "error_count": int(summary.get("error_count", 0) or 0),
            },
            "items": payload.get("items", []),
            "remaining_contracts": payload.get("remaining_contracts", []),
            "updated_at": session.updated_at.isoformat() if session.updated_at else "",
        }

    def save_manual_contract_oa_fields(self, *, updates: list[dict[str, Any]]) -> dict[str, Any]:
        """手动保存合同 OA 字段。"""
        updated_count = 0
        errors: list[dict[str, str]] = []
        validate_url = URLValidator()

        for row in updates:
            contract_id_raw = row.get("id", row.get("contract_id"))
            try:
                contract_id = int(str(contract_id_raw)) if contract_id_raw is not None else 0
            except (TypeError, ValueError):
                errors.append({"contract_id": str(contract_id_raw or ""), "message": str(_("合同ID无效"))})
                continue

            case_number = str(row.get("law_firm_oa_case_number") or "").strip()
            oa_url = str(row.get("law_firm_oa_url") or "").strip()

            if oa_url:
                try:
                    validate_url(oa_url)
                except ValidationError:
                    errors.append({"contract_id": str(contract_id), "message": str(_("律所OA链接格式无效"))})
                    continue

            with transaction.atomic():
                affected = Contract.objects.filter(id=contract_id).update(
                    law_firm_oa_case_number=case_number or None,
                    law_firm_oa_url=oa_url or None,
                )

            if affected == 0:
                errors.append({"contract_id": str(contract_id), "message": str(_("合同不存在"))})
                continue
            updated_count += 1

        return {
            "updated_count": updated_count,
            "error_count": len(errors),
            "errors": errors,
            "remaining_contracts": self.list_missing_oa_contracts(),
        }

    def run_sync_task(self, *, session_id: int) -> None:
        session = ContractOASyncSession.objects.select_related("started_by").filter(id=session_id).first()
        if session is None:
            logger.warning("contract_oa_sync_session_missing", extra={"session_id": session_id})
            return

        if session.status in {ContractOASyncStatus.COMPLETED, ContractOASyncStatus.CANCELLED}:
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
                status=ContractOASyncStatus.RUNNING,
                total_count=total_count,
                processed_count=0,
                matched_count=0,
                multiple_count=0,
                not_found_count=0,
                error_count=0,
                progress_message=str(_("正在连接金诚同达OA")),
                error_message="",
                started_at=session.started_at or timezone.now(),
                result_payload={"items": [], "summary": {}, "remaining_contracts": []},
            )

            if total_count == 0:
                logger.info("contract_oa_sync_no_contracts", extra={"session_id": session_id})
                self._update_session(
                    session,
                    status=ContractOASyncStatus.COMPLETED,
                    progress_message=str(_("没有需要同步的合同")),
                    completed_at=timezone.now(),
                    result_payload={"items": [], "summary": {}, "remaining_contracts": []},
                )
                return

            from apps.oa_filing.services.oa_scripts.jtn_case_import import JtnCaseImportScript

            script = JtnCaseImportScript(
                account=credential.account,
                password=credential.password,
                headless=not bool(os.environ.get("DISPLAY")),
            )
            ensure_name_search_ready = getattr(script, "ensure_name_search_ready", None)
            if callable(ensure_name_search_ready):
                ensure_name_search_ready()

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
                            message = str(_("合同名称为空，无法查询"))
                        else:
                            candidates = self._search_candidates_with_fallback_keywords(
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
                                message = str(_("已命中唯一候选，请人工确认后手动保存"))
                            elif len(candidates) > 1:
                                status = "multiple"
                                multiple_count += 1
                                message = str(_("命中多个结果，请人工确认"))
                            else:
                                status = "not_found"
                                not_found_count += 1
                                message = str(_("未找到匹配的OA案件"))
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
                            "session_id": session_id,
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
                            _("正在同步 (%(current)s/%(total)s): %(name)s")
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
                script.close()

            logger.info(
                "contract_oa_sync_completed",
                extra={
                    "session_id": session_id,
                    "total_count": total_count,
                    "matched_count": matched_count,
                    "multiple_count": multiple_count,
                    "not_found_count": not_found_count,
                    "error_count": error_count,
                },
            )

            self._update_session(
                session,
                status=ContractOASyncStatus.COMPLETED,
                completed_at=timezone.now(),
                progress_message=str(_("同步完成")),
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
        except Exception as exc:
            logger.exception("contract_oa_sync_failed", extra={"session_id": session_id})
            error_message = str(exc)
            sso_login_url = self._extract_sso_login_url(error_message)
            self._update_session(
                session,
                status=ContractOASyncStatus.FAILED,
                progress_message=str(_("同步失败")),
                error_message=error_message,
                completed_at=timezone.now(),
                result_payload={
                    "items": [],
                    "summary": {},
                    "remaining_contracts": self.list_missing_oa_contracts(),
                    "sso_login_url": sso_login_url,
                },
            )

    def _search_candidates_with_fallback_keywords(
        self,
        *,
        script: JtnCaseImportScript,
        contract_id: int,
        contract_name: str,
        limit: int,
    ) -> list[OAListCaseCandidate]:
        keywords = self._build_name_search_keywords(contract_name=contract_name, contract_id=contract_id)
        if not keywords:
            return []

        effective_limit = max(1, int(limit))
        expanded_limit = max(effective_limit * 5, 30)

        for keyword in keywords:
            candidates = script.search_cases_by_name(contract_name=keyword, limit=effective_limit)
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
                expanded_candidates = script.search_cases_by_name(contract_name=keyword, limit=expanded_limit)
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

    def _filter_candidates_by_contract_name(
        self,
        *,
        contract_name: str,
        candidates: list[OAListCaseCandidate],
    ) -> list[OAListCaseCandidate]:
        if not candidates:
            return []

        normalized_contract_name = self._normalize_match_text(contract_name)
        exact_name_matches = [
            candidate
            for candidate in candidates
            if self._normalize_match_text(candidate.case_name) == normalized_contract_name
        ]
        if exact_name_matches:
            return exact_name_matches

        plaintiff_tokens, defendant_tokens = self._extract_lawsuit_party_tokens(contract_name)
        if not plaintiff_tokens or not defendant_tokens:
            return candidates

        strict_filtered: list[OAListCaseCandidate] = []
        for candidate in candidates:
            candidate_name = self._normalize_match_text(candidate.case_name)
            plaintiff_hit = any(token in candidate_name for token in plaintiff_tokens)
            defendant_hit = any(token in candidate_name for token in defendant_tokens)
            if plaintiff_hit and defendant_hit:
                strict_filtered.append(candidate)

        if strict_filtered:
            return strict_filtered

        relaxed_plaintiff_markers = self._build_relaxed_party_markers(plaintiff_tokens)
        relaxed_defendant_markers = self._build_relaxed_party_markers(defendant_tokens)
        relaxed_filtered: list[OAListCaseCandidate] = []
        for candidate in candidates:
            candidate_name = self._normalize_match_text(candidate.case_name)
            plaintiff_hit = any(marker in candidate_name for marker in relaxed_plaintiff_markers)
            defendant_hit = any(marker in candidate_name for marker in relaxed_defendant_markers)
            if plaintiff_hit and defendant_hit:
                relaxed_filtered.append(candidate)

        if relaxed_filtered:
            return relaxed_filtered

        return []

    def _extract_lawsuit_party_tokens(self, contract_name: str) -> tuple[list[str], list[str]]:
        normalized_name = str(contract_name or "").strip()
        if "诉" not in normalized_name:
            return [], []

        left_part, right_part = normalized_name.split("诉", 1)
        plaintiff_tokens = self._split_party_tokens(left_part, strip_dispute=False)
        defendant_tokens = self._split_party_tokens(right_part, strip_dispute=True)
        return plaintiff_tokens, defendant_tokens

    def _split_party_tokens(self, party_text: str, *, strip_dispute: bool) -> list[str]:
        cleaned = re.sub(r"[（(][^）)]*[）)]", " ", str(party_text or "")).strip()
        if strip_dispute:
            for phrase in ("民间借贷纠纷", "买卖合同纠纷"):
                cleaned = cleaned.replace(phrase, " ")
            cleaned = re.sub(
                r"(?:合同纠纷|借贷纠纷|劳务纠纷|侵权纠纷|纠纷|争议|案件).*$",
                "",
                cleaned,
            ).strip()
        pieces = re.split(r"[、,，;；和及与以及]\s*", cleaned)
        tokens: list[str] = []

        for piece in pieces:
            token = self._normalize_match_text(piece)
            if not token:
                continue
            token = token.removesuffix("等")
            token = re.sub(r"(?:\d+|[一二三四五六七八九十百千万两]+)案$", "", token).strip()
            if "诉" in token:
                token = token.split("诉")[-1].strip()
            if len(token) < 2:
                continue
            if token not in tokens:
                tokens.append(token)

        return tokens

    def _build_relaxed_party_markers(self, tokens: list[str]) -> list[str]:
        markers: list[str] = []

        def append_marker(value: str) -> None:
            marker = self._normalize_match_text(value)
            if len(marker) < 2:
                return
            if marker not in markers:
                markers.append(marker)

        for token in tokens:
            normalized = self._normalize_match_text(token)
            if not normalized:
                continue

            append_marker(normalized)

            core = re.sub(r"(?:有限责任公司|股份有限公司|有限公司|公司|集团|分公司)$", "", normalized)
            append_marker(core)

            core = re.sub(
                r"^(?:北京|上海|天津|重庆|广东|江苏|浙江|山东|河南|河北|四川|湖北|湖南|福建|安徽|江西|广西|云南|贵州|海南|陕西|山西|辽宁|吉林|黑龙江|内蒙古|宁夏|新疆|西藏|青海|甘肃|香港|澳门)",
                "",
                core,
            )
            append_marker(core)

            if len(core) >= 2:
                append_marker(core[:2])
            if len(core) >= 3:
                append_marker(core[:3])
            if len(core) >= 4:
                append_marker(core[:4])

        return markers

    def _normalize_match_text(self, value: str) -> str:
        text = re.sub(r"\s+", "", str(value or "")).strip()
        return re.sub(r"[\-—_，,。.;；:：()（）\[\]{}]", "", text)

    def _build_name_search_keywords(self, contract_name: str, contract_id: int = 0) -> list[str]:
        raw_name = str(contract_name or "").strip()
        keywords: list[str] = []

        def append_keyword(value: str) -> None:
            text = re.sub(r"\s+", " ", str(value or "")).strip()
            if not text:
                return
            if text not in keywords:
                keywords.append(text)

        # 优先使用合同名检索；命中不足时再回退我方当事人关键词。
        if raw_name:
            plaintiff_tokens, defendant_tokens = self._extract_lawsuit_party_tokens(raw_name)
            is_lawsuit_name = bool(plaintiff_tokens and defendant_tokens)

            append_keyword(raw_name)

            without_brackets = re.sub(r"[（(][^）)]*[）)]", " ", raw_name)
            append_keyword(without_brackets)

            without_case_count = re.sub(r"(?:\d+|[一二三四五六七八九十百千万两]+)案$", "", without_brackets).strip(
                " -—_，,。.;；"
            )
            append_keyword(without_case_count)

            if is_lawsuit_name:
                for plaintiff in plaintiff_tokens:
                    for defendant in defendant_tokens:
                        append_keyword(f"{plaintiff}诉{defendant}")
                for defendant in defendant_tokens:
                    append_keyword(defendant)
            else:
                dispute_matches = re.findall(r"([\u4e00-\u9fa5A-Za-z0-9]{2,32}(?:纠纷|争议|案件))", without_case_count)
                if dispute_matches:
                    dispute_keyword = str(dispute_matches[-1]).strip()
                    append_keyword(dispute_keyword)
                    if "诉" in dispute_keyword:
                        append_keyword(dispute_keyword.split("诉")[-1].strip())

                    for explicit_phrase in ("民间借贷纠纷", "买卖合同纠纷"):
                        if explicit_phrase in dispute_keyword:
                            append_keyword(explicit_phrase)

                    tail_match = re.search(
                        r"([\u4e00-\u9fa5]{2,16}(?:合同纠纷|借贷纠纷|劳务纠纷|侵权纠纷|纠纷|争议|案件))$",
                        dispute_keyword,
                    )
                    if tail_match:
                        append_keyword(str(tail_match.group(1)).strip())

                short_tail = without_case_count[-24:]
                append_keyword(short_tail)

        party_keywords: list[str] = []
        if contract_id > 0:
            try:
                party_keywords = self._build_party_name_keywords(contract_id=contract_id)
            except RuntimeError:
                logger.debug(
                    "contract_oa_sync_skip_party_name_keywords_without_db",
                    extra={"contract_id": contract_id},
                )
        for keyword in party_keywords:
            append_keyword(keyword)

        return keywords[:10]

    def _build_party_name_keywords(self, *, contract_id: int) -> list[str]:
        party_names = (
            ContractParty.objects.filter(contract_id=contract_id, client__is_our_client=True)
            .select_related("client")
            .values_list("client__name", flat=True)
        )

        keywords: list[str] = []
        for name in party_names:
            normalized = str(name or "").strip()
            if len(normalized) < 2:
                continue
            if normalized not in keywords:
                keywords.append(normalized)

        return keywords

    def _is_stale_active_session(self, session: ContractOASyncSession) -> bool:
        if session.status not in self._ACTIVE_STATUSES:
            return False

        updated_at = session.updated_at
        if updated_at is None:
            return True

        stale_before = timezone.now() - timedelta(minutes=self._STALE_RUNNING_MINUTES)
        return bool(updated_at < stale_before)

    def _build_missing_contract_queryset(self) -> Any:
        return (
            Contract.objects.filter(
                Q(law_firm_oa_url__isnull=True)
                | Q(law_firm_oa_url="")
                | Q(law_firm_oa_case_number__isnull=True)
                | Q(law_firm_oa_case_number="")
            )
            .only("id", "name", "law_firm_oa_url", "law_firm_oa_case_number")
            .order_by("id")
        )

    def _serialize_missing_contracts(self, contracts: list[Contract]) -> list[dict[str, Any]]:
        return [
            {
                "id": int(contract.id),
                "name": str(contract.name or ""),
                "law_firm_oa_url": str(contract.law_firm_oa_url or ""),
                "law_firm_oa_case_number": str(contract.law_firm_oa_case_number or ""),
            }
            for contract in contracts
        ]

    def _fill_contract_oa_fields(self, *, contract: Contract, candidate: OAListCaseCandidate) -> None:
        with transaction.atomic():
            Contract.objects.filter(id=contract.id).update(
                law_firm_oa_case_number=str(candidate.case_no),
                law_firm_oa_url=str(candidate.detail_url),
            )

    def _resolve_oa_credential(self, *, lawyer_id: int | None) -> AccountCredential:
        from apps.organization.models import AccountCredential

        if lawyer_id is None:
            raise RuntimeError(str(_("当前用户无效，无法获取OA凭证")))

        credential = (
            AccountCredential.objects.filter(
                Q(account__icontains="jtn.com") | Q(url__icontains="jtn.com"),
                lawyer_id=lawyer_id,
            )
            .order_by("-last_login_success_at", "-id")
            .first()
        )
        if credential is None:
            raise RuntimeError(str(_("未找到金诚同达OA账号，请先在账号密码中配置")))
        return credential

    def _extract_sso_login_url(self, text: str) -> str:
        message = str(text or "")
        if "access.jtn.com" not in message:
            return ""
        url_match = re.search(r"https://access\.jtn\.com/[^\s\"'<>]+", message)
        if url_match:
            return str(url_match.group(0)).strip()
        return "https://access.jtn.com/login"

    def _update_session(self, session: ContractOASyncSession, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = timezone.now()
        ContractOASyncSession.objects.filter(id=session.id).update(**fields)
        for key, value in fields.items():
            if key != "updated_at":
                setattr(session, key, value)


def run_contract_oa_sync_task(session_id: int) -> None:
    """Django-Q 任务入口。"""
    # Playwright 同步 API 执行期间会维护事件循环，后续同步 ORM 更新进度时
    # 可能被 Django 误判为 async context。这里沿用项目内后台任务的处理方式：
    # 放开 async-unsafe 检查，并将整个同步流程隔离到独立线程执行。
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
    service = ContractOASyncService()
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="contract-oa-sync") as pool:
        future = pool.submit(service.run_sync_task, session_id=session_id)
        future.result()
