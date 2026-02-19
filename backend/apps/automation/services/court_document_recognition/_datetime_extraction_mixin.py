"""开庭时间提取 Mixin"""

import logging
from datetime import datetime
from typing import Any, cast

logger = logging.getLogger("apps.automation")

# 开庭时间正则表达式模式
DATETIME_PATTERNS = [
    (r"(\d{4})年(\d{1,2})月(\d{1,2})日\s+(上午|下午)\s*(\d{1,2})[时点](\d{1,2})分?", True),
    (r"(\d{4})年(\d{1,2})月(\d{1,2})日(上午|下午)(\d{1,2})[时点](\d{1,2})分?", True),
    (r"(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2})[时点](\d{1,2})分?", False),
    (r"(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})[时点](\d{1,2})分?", False),
    (r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{1,2})", False),
    (r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2})", False),
    (r"(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{1,2})", False),
]

HEARING_HIGH_WEIGHT_KEYWORDS = ["开庭", "庭审", "定于", "传唤"]
HEARING_MEDIUM_WEIGHT_KEYWORDS = [
    "审理", "出庭", "到庭", "准时到", "按时到", "应诉", "参加诉讼",
    "审判庭", "法庭", "第一审判庭", "第二审判庭", "第三审判庭",
    "应到时间", "到庭时间", "开庭时间",
]
HEARING_LOW_WEIGHT_KEYWORDS = ["本院", "通知", "届时", "如期", "依法"]
HEARING_CONTEXT_KEYWORDS = (
    HEARING_HIGH_WEIGHT_KEYWORDS + HEARING_MEDIUM_WEIGHT_KEYWORDS + HEARING_LOW_WEIGHT_KEYWORDS
)


class DatetimeExtractionMixin:
    """开庭时间提取 Mixin"""

    import re as _re

    def _parse_datetime_groups(
        self, groups: tuple[Any, ...], has_am_pm: bool, matched_text: str
    ) -> datetime | None:
        """解析正则分组为 datetime"""
        if has_am_pm and len(groups) == 6:
            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            am_pm, hour, minute = groups[3], int(groups[4]), int(groups[5])
            if am_pm not in ("上午", "下午"):
                logger.debug(f"无效的上午/下午标识: {am_pm}, 跳过匹配: {matched_text}")
                return None
            if am_pm == "下午" and hour < 12:
                hour += 12
            elif am_pm == "上午" and hour == 12:
                hour = 0
        elif len(groups) == 5:
            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            hour, minute = int(groups[3]), int(groups[4])
        else:
            logger.debug(f"未知的分组数量: {len(groups)}, 跳过匹配: {matched_text}")
            return None
        if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
            logger.debug(f"日期时间无效: {matched_text}")
            return None
        if not (2020 <= year <= 2030):
            logger.debug(f"年份不合理: {year}, 跳过匹配: {matched_text}")
            return None
        return datetime(year, month, day, hour, minute)

    def _extract_datetime_by_regex(self, text: str) -> list[tuple[datetime, str, float]]:
        """使用正则表达式从文本中提取日期时间"""
        import re
        results: list[tuple[datetime, str, float]] = []
        for pattern, has_am_pm in DATETIME_PATTERNS:
            for match in re.finditer(pattern, text):
                try:
                    matched_text = match.group(0)
                    dt = self._parse_datetime_groups(match.groups(), has_am_pm, matched_text)
                    if dt is None:
                        continue
                    context_score = self._calculate_context_score(text, match.start())
                    if not any(abs((dt - existing[0]).total_seconds()) < 60 for existing in results):
                        results.append((dt, matched_text, context_score))
                        logger.debug(f"正则提取到时间: {dt}, 原文: {matched_text}, 上下文得分: {context_score}")
                except (ValueError, IndexError) as e:
                    logger.debug(f"解析日期时间失败: {match.group(0)}, 错误: {e}")
                    continue
        return results

    def _calculate_context_score(self, text: str, match_position: int) -> int:
        """计算匹配位置的上下文得分（0-100）"""
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

    def _score_days_diff(self, days_diff: int, score: int, reasons: list[str]) -> tuple[int, list[str]]:
        """评估天数差对分数的影响"""
        if days_diff < -7:
            reasons.append(f"时间已过去{abs(days_diff)}天")
            score -= 30
        elif days_diff < 0:
            reasons.append(f"时间已过去{abs(days_diff)}天")
            score -= 10
        elif days_diff > 365 * 2:
            reasons.append(f"时间在{days_diff}天后，超过2年")
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
        return score, reasons

    def _validate_hearing_datetime(self, dt: datetime) -> tuple[bool, int, str]:
        """校验开庭时间的合理性"""
        now = datetime.now()
        score = 50
        reasons: list[str] = []
        days_diff = (dt.date() - now.date()).days
        score, reasons = self._score_days_diff(days_diff, score, reasons)
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
        if dt.weekday() >= 5:
            score -= 10
            reasons.append("周末")
        else:
            score += 5
            reasons.append("工作日")
        if dt.minute in {0, 30}:
            score += 10
            reasons.append("整点/半点")
        elif dt.minute in {15, 45}:
            score += 5
            reasons.append("刻钟")
        score = max(0, min(100, score))
        return score > 30, score, "; ".join(reasons)

    def _validate_regex_results(
        self, regex_results: list[tuple[datetime, str, int | float]]
    ) -> list[dict[str, Any]]:
        """对正则结果进行合理性校验和综合评分"""
        validated: list[dict[str, Any]] = []
        for dt, matched_text, context_score in regex_results:
            is_valid, validity_score, validity_reason = self._validate_hearing_datetime(dt)
            combined_score = context_score * 0.6 + validity_score * 0.4
            validated.append({
                "datetime": dt,
                "matched_text": matched_text,
                "context_score": context_score,
                "validity_score": validity_score,
                "validity_reason": validity_reason,
                "combined_score": combined_score,
                "is_valid": is_valid,
            })
            logger.debug(
                f"正则候选: {dt}, 上下文={context_score}, 合理性={validity_score}({validity_reason}), "
                f"综合={combined_score:.1f}, 有效={is_valid}"
            )
        return validated

    def _select_best_from_conflict(
        self,
        best_regex_dt: datetime,
        best_regex_combined: float,
        ollama_datetime: datetime,
        ollama_validity_score: int,
        valid_regex_results: list[dict[str, Any]],
    ) -> tuple[datetime | None, str]:
        """处理正则与 Ollama 结果冲突"""
        date_diff = abs((best_regex_dt.date() - ollama_datetime.date()).days)
        time_diff = abs((best_regex_dt - ollama_datetime).total_seconds())
        if date_diff == 0 and time_diff < 3600:
            logger.info(f"正则和Ollama结果一致: {best_regex_dt}")
            return best_regex_dt, "regex+ollama(一致)"
        if date_diff == 0:
            logger.warning(f"时间冲突: 正则={best_regex_dt}, Ollama={ollama_datetime}, 时间差={time_diff}秒")
            if best_regex_combined >= 40:
                return best_regex_dt, f"regex(score={best_regex_combined:.0f},时间冲突)"
            return ollama_datetime, f"ollama(validity={ollama_validity_score},时间冲突,正则得分低)"
        logger.warning(f"日期冲突: 正则={best_regex_dt.date()}, Ollama={ollama_datetime.date()}, 差异={date_diff}天")
        for result in valid_regex_results[1:]:
            result_dt = cast(datetime, result["datetime"])
            if abs((result_dt.date() - ollama_datetime.date()).days) == 0:
                logger.info(f"找到与Ollama一致的备选正则结果: {result['datetime']}")
                return result_dt, f"regex(score={result['combined_score']:.0f},与ollama一致)"
        if best_regex_combined >= 60:
            return best_regex_dt, f"regex(score={best_regex_combined:.0f},日期冲突)"
        if ollama_validity_score >= 50:
            return ollama_datetime, f"ollama(validity={ollama_validity_score},日期冲突)"
        if best_regex_combined >= ollama_validity_score:
            return best_regex_dt, f"regex(score={best_regex_combined:.0f},低置信度)"
        return ollama_datetime, f"ollama(validity={ollama_validity_score},低置信度)"

    def _select_best_datetime(
        self, regex_results: list[tuple[datetime, str, int | float]], ollama_datetime: datetime | None
    ) -> tuple[datetime | None, str]:
        """从正则提取结果和 Ollama 结果中选择最佳时间"""
        if not regex_results and not ollama_datetime:
            return None, "无法提取"
        validated_regex_results = self._validate_regex_results(regex_results)
        valid_regex_results = sorted(
            [r for r in validated_regex_results if r["is_valid"]],
            key=lambda x: float(x["combined_score"]),
            reverse=True,
        )
        ollama_valid = False
        ollama_validity_score = 0
        ollama_validity_reason = ""
        if ollama_datetime:
            ollama_valid, ollama_validity_score, ollama_validity_reason = (
                self._validate_hearing_datetime(ollama_datetime)
            )
            logger.debug(
                f"Ollama候选: {ollama_datetime},"
                f" 合理性={ollama_validity_score}({ollama_validity_reason}), 有效={ollama_valid}"
            )
        if not valid_regex_results:
            if ollama_datetime and ollama_valid:
                logger.info(f"仅使用 Ollama 结果: {ollama_datetime} (合理性={ollama_validity_score})")
                return ollama_datetime, f"ollama(validity={ollama_validity_score})"
            if ollama_datetime:
                logger.warning(f"Ollama 结果合理性较低: {ollama_datetime} ({ollama_validity_reason})")
                return ollama_datetime, f"ollama(低合理性:{ollama_validity_reason})"
            if validated_regex_results:
                best_invalid = max(validated_regex_results, key=lambda x: float(x["combined_score"]))
                logger.warning(
                    f"所有正则结果合理性较低，使用最佳候选:"
                    f" {best_invalid['datetime']} ({best_invalid['validity_reason']})"
                )
                return (
                    cast(datetime, best_invalid["datetime"]),
                    f"regex(低合理性:{best_invalid['validity_reason']})",
                )
            return None, "无法提取"
        best_regex = valid_regex_results[0]
        best_regex_dt = cast(datetime, best_regex["datetime"])
        best_regex_combined = float(best_regex["combined_score"])
        if not ollama_datetime or not ollama_valid:
            logger.info(f"使用正则结果: {best_regex_dt}, 综合得分={best_regex_combined:.1f}")
            return best_regex_dt, f"regex(score={best_regex_combined:.0f})"
        return self._select_best_from_conflict(
            best_regex_dt, best_regex_combined, ollama_datetime, ollama_validity_score, valid_regex_results
        )
