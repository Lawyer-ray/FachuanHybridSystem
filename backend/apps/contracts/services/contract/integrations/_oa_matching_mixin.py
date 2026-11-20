"""OA 案件匹配（``ContractOASyncService`` 的 候选过滤 / 当事人分词 / 关键词构造 / 名称归一化）。

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

from apps.contracts.models import ContractParty

from ._oa_service_contract import _OAServiceContract

if TYPE_CHECKING:
    from apps.oa_filing.services.oa_scripts.jtn.case_import import OAListCaseCandidate

logger = logging.getLogger(__name__)


class _OAMatchingMixin(_OAServiceContract):
    """子域 mixin：具体方法见 ``contract_oa_sync_service.ContractOASyncService``。"""

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
        pieces = re.split(r"[、,，;；和及与以]\s*", cleaned)
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
