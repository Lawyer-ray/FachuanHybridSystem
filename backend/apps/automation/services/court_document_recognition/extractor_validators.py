"""
信息提取器校验模块

提供案号和开庭时间的校验方法.
作为 InfoExtractor 的 Mixin 使用.
"""

import logging
import re
from datetime import datetime
from typing import Any

from .extractor_patterns import (
    HEARING_HIGH_WEIGHT_KEYWORDS,
    HEARING_LOW_WEIGHT_KEYWORDS,
    HEARING_MEDIUM_WEIGHT_KEYWORDS,
)

logger = logging.getLogger("apps.automation")


class ExtractorValidatorsMixin:
    """信息提取器校验 Mixin

    提供校验相关的方法:
    - 案号验证
    - 开庭时间合理性校验
    - 上下文得分计算
    - 最佳时间选择
    """

    def _validate_case_number_in_text(self, case_number: str, text: str) -> bool:
        """
        验证案号是否真的存在于原文中

        防止 Ollama 幻觉生成不存在的案号.
        验证策略:检查案号中的关键部分(年份+序号)是否在原文中出现.

        Args:
            case_number: 待验证的案号
            text: 原始文本

        Returns:
            bool: 案号是否在原文中存在
        """
        if not case_number or not text:
            return False
        year_match = re.search("[(\\(](\\d{4})[)\\)]", case_number)
        seq_match = re.search("(\\d{3,})号?$", case_number)
        if not year_match or not seq_match:
            logger.debug(f"无法从案号中提取年份或序号: {case_number}")
            return False
        year = year_match.group(1)
        seq = seq_match.group(1)
        year_patterns: list[Any] = [f"({year})", f"({year})", f"〔{year}〕", f"[{year}]"]
        year_found = any(p in text for p in year_patterns)
        seq_found = seq in text
        if year_found and seq_found:
            logger.debug(f"案号验证通过: 年份={year}, 序号={seq}")
            return True
        else:
            logger.debug(f"案号验证失败: 年份={year}(found={year_found}), 序号={seq}(found={seq_found})")
            return False

    def _calculate_context_score(self, text: str, match_position: int) -> int:
        """
        计算匹配位置的上下文得分

        根据匹配位置附近是否有开庭相关关键词来计算得分.
        使用分层权重:高权重25分,中权重15分,低权重8分.

        Args:
            text: 完整文本
            match_position: 匹配位置

        Returns:
            上下文得分(0-100)
        """
        context_start = max(0, match_position - 100)
        context_end = min(len(text), match_position + 50)
        context = text[context_start:context_end]
        score = 0
        for keyword in HEARING_HIGH_WEIGHT_KEYWORDS:
            if keyword in context:
                score += 25
        for keyword in HEARING_MEDIUM_WEIGHT_KEYWORDS:
            if keyword in context:
                score += 15
        for keyword in HEARING_LOW_WEIGHT_KEYWORDS:
            if keyword in context:
                score += 8
        return min(score, 100)

    def _validate_hearing_datetime(self, dt: datetime) -> tuple[bool, int, str]:
        """
        校验开庭时间的合理性

        Args:
            dt: 待校验的时间

        Returns:
            (是否有效, 合理性得分0-100, 校验说明)
        """
        now = datetime.now()
        score = 50
        reasons: list[Any] = []
        score, reasons = self._score_date_range(dt, now, score, reasons)
        score, reasons = self._score_work_hours(dt, score, reasons)
        score, reasons = self._score_weekday(dt, score, reasons)
        score, reasons = self._score_minute(dt, score, reasons)
        score = max(0, min(100, score))
        is_valid = score > 30
        return (is_valid, score, "; ".join(reasons))

    def _score_date_range(self, dt: datetime, now: datetime, score: int, reasons: list[Any]) -> tuple[int, list[Any]]:
        """评估日期范围合理性"""
        days_diff = (dt.date() - now.date()).days
        if days_diff < -7:
            reasons.append(f"时间已过去{abs(days_diff)}天")
            score -= 30
        elif days_diff < 0:
            reasons.append(f"时间已过去{abs(days_diff)}天")
            score -= 10
        elif days_diff > 365 * 2:
            reasons.append(f"时间在{days_diff}天后,超过2年")
            score -= 40
        elif days_diff > 365:
            reasons.append(f"时间在{days_diff}天后")
            score -= 15
        elif days_diff > 180:
            reasons.append(f"时间在{days_diff}天后")
            score -= 5
        else:
            reasons.append(f"时间在{days_diff}天后")
            score += 20
        return (score, reasons)

    def _score_work_hours(self, dt: datetime, score: int, reasons: list[Any]) -> tuple[int, list[Any]]:
        """评估是否在工作时间"""
        hour = dt.hour
        if 8 <= hour <= 18:
            score += 15
            reasons.append("工作时间内")
        elif 7 <= hour < 8 or 18 < hour <= 20:
            score += 5
            reasons.append("边缘工作时间")
        else:
            score -= 20
            reasons.append(f"非工作时间({hour}点)")
        return (score, reasons)

    def _score_weekday(self, dt: datetime, score: int, reasons: list[Any]) -> tuple[int, list[Any]]:
        """评估是否是工作日"""
        if dt.weekday() >= 5:
            score -= 10
            reasons.append("周末")
        else:
            score += 5
            reasons.append("工作日")
        return (score, reasons)

    def _score_minute(self, dt: datetime, score: int, reasons: list[Any]) -> tuple[int, list[Any]]:
        """评估分钟是否合理"""
        minute = dt.minute
        if minute in {0, 30}:
            score += 10
            reasons.append("整点/半点")
        elif minute in {15, 45}:
            score += 5
            reasons.append("刻钟")
        return (score, reasons)

    def _select_best_datetime(
        self, regex_results: list[tuple[datetime, str, int]], ollama_datetime: datetime | None
    ) -> tuple[datetime | None, str]:
        """
        从正则提取结果和 Ollama 结果中选择最佳时间

        交叉校验机制:
        1. 对所有候选时间进行合理性校验
        2. 如果正则和 Ollama 结果一致(日期相同),使用该结果
        3. 如果不一致,综合考虑上下文得分和合理性得分
        4. 如果正则没有结果,使用 Ollama 结果(需通过合理性校验)

        Args:
            regex_results: 正则提取结果列表
            ollama_datetime: Ollama 提取的时间

        Returns:
            (最佳时间, 提取方法描述)
        """
        if not regex_results and (not ollama_datetime):
            return (None, "无法提取")
        validated_regex_results: list[Any] = []
        for dt, matched_text, context_score in regex_results:
            is_valid, validity_score, validity_reason = self._validate_hearing_datetime(dt)
            combined_score = context_score * 0.6 + validity_score * 0.4
            validated_regex_results.append(
                {
                    "datetime": dt,
                    "matched_text": matched_text,
                    "context_score": context_score,
                    "validity_score": validity_score,
                    "validity_reason": validity_reason,
                    "combined_score": combined_score,
                    "is_valid": is_valid,
                }
            )
            logger.debug(
                f"正则候选: {dt}, 上下文={context_score}, 合理性={validity_score}"
                f"({validity_reason}), 综合={combined_score:.1f}, 有效={is_valid}"
            )
        valid_regex_results: list[Any] = []
        valid_regex_results.sort(key=lambda x: x["combined_score"], reverse=True)
        ollama_valid = False
        ollama_validity_score = 0
        ollama_validity_reason = ""
        if ollama_datetime:
            ollama_valid, ollama_validity_score, ollama_validity_reason = self._validate_hearing_datetime(
                ollama_datetime
            )
            logger.debug(
                f"Ollama候选: {ollama_datetime}, 合理性={ollama_validity_score}"
                f"({ollama_validity_reason}), 有效={ollama_valid}"
            )
        if not valid_regex_results:
            return self._handle_ollama_only_result(
                ollama_datetime, ollama_valid, ollama_validity_score, ollama_validity_reason, validated_regex_results
            )
        best_regex = valid_regex_results[0]
        best_regex_dt = best_regex["datetime"]
        best_regex_combined = best_regex["combined_score"]
        if not ollama_datetime or not ollama_valid:
            logger.info(
                f"使用正则结果: {best_regex_dt}, 综合得分={best_regex_combined:.1f}"
                f" (上下文={best_regex['context_score']}, 合理性={best_regex['validity_score']})"
            )
            return (best_regex_dt, f"regex(score={best_regex_combined:.0f})")
        return self._cross_validate_results(best_regex, valid_regex_results, ollama_datetime, ollama_validity_score)

    def _handle_ollama_only_result(
        self,
        ollama_datetime: Any,
        ollama_valid: Any,
        ollama_validity_score: Any,
        ollama_validity_reason: Any,
        validated_regex_results: Any,
    ) -> tuple[datetime | None, str]:
        """处理只有 Ollama 结果的情况"""
        if ollama_datetime and ollama_valid:
            logger.info(f"仅使用 Ollama 结果: {ollama_datetime} (合理性={ollama_validity_score})")
            return (ollama_datetime, f"ollama(validity={ollama_validity_score})")
        elif ollama_datetime:
            logger.warning(f"Ollama 结果合理性较低: {ollama_datetime} ({ollama_validity_reason})")
            return (ollama_datetime, f"ollama(低合理性:{ollama_validity_reason})")
        else:
            if validated_regex_results:
                best_invalid = max(validated_regex_results, key=lambda x: x["combined_score"])
                logger.warning(
                    f"所有正则结果合理性较低,使用最佳候选: {best_invalid['datetime']}"
                    f" ({best_invalid['validity_reason']})"
                )
                return (best_invalid["datetime"], f"regex(低合理性:{best_invalid['validity_reason']})")
            return (None, "无法提取")

    def _cross_validate_results(
        self, best_regex: Any, valid_regex_results: Any, ollama_datetime: Any, ollama_validity_score: Any
    ) -> tuple[datetime | None, str]:
        """交叉校验正则和 Ollama 结果"""
        best_regex_dt = best_regex["datetime"]
        best_regex_combined = best_regex["combined_score"]
        date_diff = abs((best_regex_dt.date() - ollama_datetime.date()).days)
        time_diff = abs((best_regex_dt - ollama_datetime).total_seconds())
        if date_diff == 0 and time_diff < 3600:
            logger.info(f"正则和Ollama结果一致: {best_regex_dt}")
            return (best_regex_dt, "regex+ollama(一致)")
        if date_diff == 0:
            logger.warning(f"时间冲突: 正则={best_regex_dt}, Ollama={ollama_datetime}, 时间差={time_diff}秒")
            if best_regex_combined >= 40:
                return (best_regex_dt, f"regex(score={best_regex_combined:.0f},时间冲突)")
            else:
                return (ollama_datetime, f"ollama(validity={ollama_validity_score},时间冲突,正则得分低)")
        logger.warning(f"日期冲突: 正则={best_regex_dt.date()}, Ollama={ollama_datetime.date()}, 差异={date_diff}天")
        for result in valid_regex_results[1:]:
            if abs((result["datetime"].date() - ollama_datetime.date()).days) == 0:
                logger.info(f"找到与Ollama一致的备选正则结果: {result['datetime']}")
                return (result["datetime"], f"regex(score={result['combined_score']:.0f},与ollama一致)")
        if best_regex_combined >= 60:
            return (best_regex_dt, f"regex(score={best_regex_combined:.0f},日期冲突)")
        elif ollama_validity_score >= 50:
            return (ollama_datetime, f"ollama(validity={ollama_validity_score},日期冲突)")
        elif best_regex_combined >= ollama_validity_score:
            return (best_regex_dt, f"regex(score={best_regex_combined:.0f},低置信度)")
        else:
            return (ollama_datetime, f"ollama(validity={ollama_validity_score},低置信度)")
