"""
法院短信推荐关联案件服务

基于聚合搜索（案号、法院名称、当事人）为 CourtSMS 推荐可能关联的案件.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from django.db.models import Q, QuerySet

from apps.automation.models.court_sms import CourtSMS
from apps.automation.utils.text_utils import TextUtils
from apps.cases.models.case import Case
from apps.core.models.enums import CaseStatus

logger = logging.getLogger("apps.automation")

# 短信内容中法院名称的正则（以"人民法院"结尾）
_COURT_NAME_PATTERN = re.compile(r"[一-龥]{2,15}人民法院")

# 案号中提取年份+法院代码前缀的正则
# 匹配：(2025)粤0605 → 前缀 "(2025)粤0605"
_YEAR_COURT_PREFIX_PATTERN = re.compile(r"[(（](\d{4})[)）]([一-龥]{1,6}\d{0,4})")


@dataclass
class RecommendationResult:
    """推荐结果数据类"""

    case_id: int
    case_name: str
    score: int
    reasons: list[str] = field(default_factory=list)
    case_numbers: list[str] = field(default_factory=list)
    parties: list[str] = field(default_factory=list)
    court_names: list[str] = field(default_factory=list)
    status: str = ""


class CourtSMSRecommendationService:
    """法院短信推荐关联案件服务"""

    def get_recommendations(self, sms: CourtSMS) -> list[RecommendationResult]:
        """获取推荐关联案件列表"""
        normalized_numbers = [TextUtils.normalize_case_number(n) for n in (sms.case_numbers or []) if n.strip()]
        year_court_prefixes = self._collect_year_court_prefixes(normalized_numbers)
        court_name = self._extract_court_name(sms)
        party_names = [p.strip() for p in (sms.party_names or []) if p.strip()]

        q = self._build_query(normalized_numbers, year_court_prefixes, court_name, party_names)
        if not q:
            return []

        candidates = (
            Case.objects.filter(q, status=CaseStatus.ACTIVE)
            .distinct()
            .prefetch_related("case_numbers", "parties__client", "supervising_authorities")
        )

        results = self._score_and_rank(candidates, normalized_numbers, year_court_prefixes, court_name, party_names)
        logger.info(
            "推荐关联案件: SMS ID=%s, 候选=%d, 返回=%d",
            sms.id,
            candidates.count(),
            len(results),
        )
        return results

    # -- 法院名称提取 --

    def _extract_court_name(self, sms: CourtSMS) -> str | None:
        """从短信关联数据中提取法院名称（三级回退）"""
        # 优先级 1：CourtDocument.c_fymc（最准确）
        court_name = self._extract_court_name_from_document(sms)
        if court_name:
            return court_name

        # 优先级 2：短信内容正则提取
        court_name = self._extract_court_name_from_content(sms.content or "")
        if court_name:
            return court_name

        return None

    def _extract_court_name_from_document(self, sms: CourtSMS) -> str | None:
        """从关联的 CourtDocument 中提取法院名称"""
        try:
            task = sms.scraper_task
            if not task:
                return None
            documents = getattr(task, "documents", None)
            if not documents:
                return None
            court_doc = documents.filter(c_fymc__isnull=False).exclude(c_fymc="").first()
            if court_doc and court_doc.c_fymc:
                return str(court_doc.c_fymc)
        except Exception:
            pass
        return None

    def _extract_court_name_from_content(self, content: str) -> str | None:
        """从短信内容中用正则提取法院名称"""
        match = _COURT_NAME_PATTERN.search(content)
        return match.group(0) if match else None

    # -- 案号前缀提取 --

    @staticmethod
    def _collect_year_court_prefixes(normalized_numbers: list[str]) -> list[str]:
        """从规范化的案号中提取年份+法院代码前缀"""
        prefixes: list[str] = []
        for number in normalized_numbers:
            match = _YEAR_COURT_PREFIX_PATTERN.search(number)
            if match:
                prefix = f"({match.group(1)}){match.group(2)}"
                if prefix not in prefixes:
                    prefixes.append(prefix)
        return prefixes

    # -- 查询构建 --

    @staticmethod
    def _build_query(
        normalized_numbers: list[str],
        year_court_prefixes: list[str],
        court_name: str | None,
        party_names: list[str],
    ) -> Q | None:
        """构建多维度 OR 查询"""
        q = Q()

        # 查询 1：案号精确匹配
        if normalized_numbers:
            q |= Q(case_numbers__number__in=normalized_numbers)

        # 查询 2：案号前缀模糊匹配（同法院同年度）
        for prefix in year_court_prefixes:
            q |= Q(case_numbers__number__icontains=prefix)

        # 查询 3：法院名称匹配
        if court_name:
            q |= Q(supervising_authorities__name__icontains=court_name)

        # 查询 4：当事人名称匹配（宽松单向匹配）
        for name in party_names:
            if len(name) >= 2:
                q |= Q(parties__client__name__icontains=name)

        return q if q else None

    # -- 评分排序 --

    def _score_and_rank(
        self,
        candidates: QuerySet[Case],
        normalized_numbers: list[str],
        year_court_prefixes: list[str],
        court_name: str | None,
        party_names: list[str],
    ) -> list[RecommendationResult]:
        """对候选案件评分排序，返回 top 10"""
        results: list[tuple[Case, int, list[str]]] = []
        seen_ids: set[int] = set()

        for case in candidates:
            if case.id in seen_ids:
                continue
            seen_ids.add(case.id)
            score, reasons = self._score_case(case, normalized_numbers, year_court_prefixes, court_name, party_names)
            results.append((case, score, reasons))

        results.sort(key=lambda x: (-x[1], -x[0].id))

        return [self._build_result(case, score, reasons) for case, score, reasons in results[:10]]

    def _score_case(
        self,
        case: Case,
        normalized_numbers: list[str],
        year_court_prefixes: list[str],
        court_name: str | None,
        party_names: list[str],
    ) -> tuple[int, list[str]]:
        """计算单个案件的匹配分数"""
        score = 0
        reasons: list[str] = []

        # 信号 1：案号匹配
        case_nums = [cn.number for cn in case.case_numbers.all()]
        normalized_case_nums = [TextUtils.normalize_case_number(n) for n in case_nums]

        if any(n in normalized_numbers for n in normalized_case_nums):
            score += 100
            reasons.append("案号完全匹配")
        elif any(any(prefix in cn for cn in normalized_case_nums) for prefix in year_court_prefixes):
            score += 50
            reasons.append("案号前缀匹配")

        # 信号 2：法院名称匹配
        if court_name:
            for sa in case.supervising_authorities.all():
                if sa.name and court_name in sa.name:
                    score += 40
                    reasons.append("法院名称匹配")
                    break

        # 信号 3：当事人匹配
        case_party_names = [cp.client.name for cp in case.parties.all() if cp.client]
        overlap = sum(1 for p in party_names if any(p in cpn for cpn in case_party_names))
        if overlap > 0:
            score += 20 * overlap
            reasons.append(f"当事人匹配({overlap}人)")

        # 时间新鲜度（近 5 年内创建的案件加分更多）
        if case.start_date:
            days = (date.today() - case.start_date).days
            recency = max(1, min(5, 5 - int(days / 365)))
            score += recency

        return score, reasons

    def _build_result(self, case: Case, score: int, reasons: list[str]) -> RecommendationResult:
        """构建推荐结果"""
        return RecommendationResult(
            case_id=case.id,
            case_name=case.name,
            score=score,
            reasons=reasons,
            case_numbers=[cn.number for cn in case.case_numbers.all()],
            parties=[cp.client.name for cp in case.parties.all() if cp.client],
            court_names=[sa.name for sa in case.supervising_authorities.all() if sa.name],
            status=case.status,
        )
