"""Business logic services."""

from __future__ import annotations

"""
交费通知书检测器

负责识别PDF页面是否为交费通知书.
"""


import logging
from typing import Any, ClassVar

from .models import DetectionResult

logger = logging.getLogger("apps.fee_notice")


class FeeNoticeDetector:
    """交费通知书检测器"""

    # 交费通知书关键词(按优先级排序)
    NOTICE_KEYWORDS: ClassVar = [
        "交费通知书",
        "缴费通知书",
        "诉讼费用交纳通知",
        "案件受理费",
    ]

    # 关键词权重配置
    KEYWORD_WEIGHTS: ClassVar = {
        "交费通知书": 1.0,
        "缴费通知书": 1.0,
        "诉讼费用交纳通知": 0.9,
        "案件受理费": 0.6,
    }

    # 置信度阈值
    CONFIDENCE_THRESHOLD = 0.5

    def detect(self, text: str, page_num: int) -> DetectionResult:
        """
        检测文本是否为交费通知书

        Args:
            text: 页面文本内容
            page_num: 页码

        Returns:
            DetectionResult: 检测结果,包含是否为通知书、置信度、匹配关键词
        """
        if not text or not text.strip():
            logger.debug("页面文本为空", extra={})
            return DetectionResult(
                is_fee_notice=False,
                page_num=page_num,
                confidence=0.0,
                matched_keywords=[],
                raw_text=text or "",
            )

        # 检测匹配的关键词
        matched_keywords = self._find_matched_keywords(text)

        # 计算置信度
        confidence = self._calculate_confidence(matched_keywords)

        # 判断是否为交费通知书
        is_fee_notice = confidence >= self.CONFIDENCE_THRESHOLD

        if is_fee_notice:
            logger.info(
                "检测到交费通知书",
                extra={
                    "page_num": page_num,
                    "matched_keywords": matched_keywords,
                    "confidence": confidence,
                },
            )
        else:
            logger.debug(
                "未检测到交费通知书",
                extra={
                    "page_num": page_num,
                    "matched_keywords": matched_keywords,
                    "confidence": confidence,
                },
            )

        return DetectionResult(
            is_fee_notice=is_fee_notice,
            page_num=page_num,
            confidence=confidence,
            matched_keywords=matched_keywords,
            raw_text=text,
        )

    def detect_pages(
        self,
        pages: list[tuple[int, str]],
    ) -> list[DetectionResult]:
        """
        批量检测多个页面

        Args:
            pages: [(页码, 文本内容), ...]

        Returns:
            List[DetectionResult]: 检测结果列表
        """
        results: list[Any] = []
        for page_num, text in pages:
            result = self.detect(text, page_num)
            results.append(result)

        # 统计检测结果
        detected_count = sum(1 for r in results if r.is_fee_notice)
        logger.info(
            "批量检测完成",
            extra={
                "total_pages": len(pages),
                "detected_count": detected_count,
            },
        )

        return results

    def _find_matched_keywords(self, text: str) -> list[str]:
        """
        查找文本中匹配的关键词

        Args:
            text: 文本内容

        Returns:
            List[str]: 匹配到的关键词列表
        """
        matched: list[Any] = []
        for keyword in self.NOTICE_KEYWORDS:
            if keyword in text:
                matched.append(keyword)
        return matched

    def _calculate_confidence(self, matched_keywords: list[str]) -> Any:
        """
        根据匹配的关键词计算置信度

        置信度计算规则:
        - 取所有匹配关键词中最高的权重作为基础置信度
        - 如果匹配多个关键词,额外增加置信度(最多增加0.2)

        Args:
            matched_keywords: 匹配到的关键词列表

        Returns:
            float: 置信度 0-1
        """
        if not matched_keywords:
            return 0.0

        # 获取最高权重
        max_weight = max(self.KEYWORD_WEIGHTS.get(kw, 0.5) for kw in matched_keywords)

        # 多关键词匹配奖励
        bonus = min(0.2, (len(matched_keywords) - 1) * 0.1)

        # 最终置信度不超过1.0
        confidence = min(1.0, max_weight + bonus)

        return round(confidence, 2)
