"""文书识别的案件匹配服务（对齐法院短信 CaseMatcher 纪律）

自动绑定只走严格匹配：案号规范化后**精确相等** + 案件**在办** + 匹配**唯一**，
三者同时满足才自动绑定；否则转人工（由推荐卡片 + 搜索兜底）。

推荐评分复用 automation 的 CourtSMSRecommendationService.get_recommendations_for_signals
（案号完全 +100 / 前缀 +50 / 法院名 +40 / 当事人 ×20 / 新鲜度），保证两个入口
（法院短信 / 文书识别）的推荐口径一致。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("apps.document_recognition")


class DocumentCaseMatchingService:
    """文书识别的案件匹配（严格自动匹配 + 推荐候选）。"""

    def __init__(self, case_service: Any | None = None):
        self._case_service = case_service

    @property
    def case_service(self) -> Any:
        if self._case_service is None:
            from apps.core.interfaces import ServiceLocator

            self._case_service = ServiceLocator.get_case_service()
        return self._case_service

    def auto_match(self, case_number: str) -> tuple[int, str] | None:
        """严格匹配：返回 (case_id, case_name)；不满足唯一在办精确匹配时返回 None。

        与旧 find_case_by_number（icontains 取第一个、不校验状态）的区别：
        - 案号规范化后精确相等（不是包含）
        - 仅在办案件
        - 唯一命中才自动绑（多个在办/唯一已结案 → 转人工）
        """
        from apps.automation.utils.text_utils import TextUtils

        normalized = TextUtils.normalize_case_number((case_number or "").strip())
        if not normalized:
            return None

        try:
            dtos = self.case_service.search_cases_by_case_number_internal(normalized)
        except Exception as e:
            logger.error("案号检索失败: %s", e, extra={"action": "auto_match", "case_number": normalized})
            return None

        active_exact = [
            d
            for d in dtos
            if d.status == "active" and TextUtils.normalize_case_number(d.case_number or "") == normalized
        ]
        if len(active_exact) != 1:
            logger.info(
                "自动匹配未命中唯一在办案件，转人工",
                extra={
                    "action": "auto_match",
                    "case_number": normalized,
                    "exact_active_count": len(active_exact),
                    "total_count": len(dtos),
                },
            )
            return None

        matched = active_exact[0]
        return matched.id, matched.name

    def get_recommendations(
        self,
        *,
        case_number: str | None,
        party_names: list[str] | None,
        raw_text: str = "",
    ) -> list[dict[str, Any]]:
        """未绑定时的推荐候选（Top10，带评分与理由），信号来自识别结果。"""
        from apps.automation.services.sms.court_sms_recommendation_service import CourtSMSRecommendationService

        case_numbers = [case_number] if case_number and case_number.strip() else []
        court_name = CourtSMSRecommendationService.extract_court_name_from_text(raw_text or "")
        results = CourtSMSRecommendationService().get_recommendations_for_signals(
            case_numbers=case_numbers,
            party_names=list(party_names or []),
            court_name=court_name,
        )
        return [
            {
                "case_id": r.case_id,
                "case_name": r.case_name,
                "score": r.score,
                "reasons": r.reasons,
                "case_numbers": r.case_numbers,
                "parties": r.parties,
                "status": r.status,
            }
            for r in results
        ]
