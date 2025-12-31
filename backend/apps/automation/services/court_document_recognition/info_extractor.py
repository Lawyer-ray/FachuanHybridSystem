"""
关键信息提取器

调用 Ollama 大模型从法院文书中提取关键信息（案号、开庭时间等）。
支持正则表达式提取和 Ollama 交叉校验机制。

Requirements: 4.3, 4.4, 4.7
"""
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from apps.core.exceptions import ServiceUnavailableError, RecognitionTimeoutError
from apps.automation.services.ai.ollama_client import chat
from apps.automation.services.ai import get_ollama_model, get_ollama_base_url

logger = logging.getLogger("apps.automation")


# 开庭时间正则表达式模式（模块级别常量）
# 注意：模式顺序很重要，更具体的模式应该放在前面
# 每个模式返回的分组数量：6组（带上午/下午）或 5组（标准格式）
DATETIME_PATTERNS = [
    # 带上午/下午（有空格）：2025年1月15日 上午 9时30分
    (r'(\d{4})年(\d{1,2})月(\d{1,2})日\s+(上午|下午)\s*(\d{1,2})[时点](\d{1,2})分?', True),
    # 带上午/下午（无空格）：2025年1月15日上午9时30分
    (r'(\d{4})年(\d{1,2})月(\d{1,2})日(上午|下午)(\d{1,2})[时点](\d{1,2})分?', True),
    # 标准中文格式（有空格）：2025年1月15日 9时30分
    (r'(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2})[时点](\d{1,2})分?', False),
    # 标准中文格式（无空格）：2025年1月15日9时30分
    (r'(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})[时点](\d{1,2})分?', False),
    # 冒号格式：2025年1月15日 9:30
    (r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{1,2})', False),
    # ISO格式：2025-01-15 09:30
    (r'(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2})', False),
    # 斜杠格式：2025/01/15 09:30
    (r'(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{1,2})', False),
]

# 开庭时间上下文关键词（按重要性分组）
# 高权重关键词（直接表明开庭时间）
HEARING_HIGH_WEIGHT_KEYWORDS = [
    '开庭', '庭审', '定于', '传唤',
]

# 中权重关键词（间接表明开庭时间）
HEARING_MEDIUM_WEIGHT_KEYWORDS = [
    '审理', '出庭', '到庭', '准时到', '按时到', '应诉', '参加诉讼',
    '审判庭', '法庭', '第一审判庭', '第二审判庭', '第三审判庭',
    '应到时间', '到庭时间', '开庭时间',  # 新增：OCR 常见格式
]

# 低权重关键词（一般性上下文）
HEARING_LOW_WEIGHT_KEYWORDS = [
    '本院', '通知', '届时', '如期', '依法',
]

# 合并所有关键词（兼容旧代码）
HEARING_CONTEXT_KEYWORDS = (
    HEARING_HIGH_WEIGHT_KEYWORDS + 
    HEARING_MEDIUM_WEIGHT_KEYWORDS + 
    HEARING_LOW_WEIGHT_KEYWORDS
)


# 案号正则表达式模式（模块级别常量）
# 案号格式：（年份）法院代码+案件类型+序号+号
# 例如：（2024）京0105民初12345号、(2024)粤0604民初41257号
CASE_NUMBER_PATTERNS = [
    # 标准格式：（2024）京0105民初12345号（中文括号）
    r'（(\d{4})）([^\s（）\(\)]{2,20}?)(\d+)号',
    # 标准格式：(2024)京0105民初12345号（英文括号）
    r'\((\d{4})\)([^\s（）\(\)]{2,20}?)(\d+)号',
    # 无括号格式：2024京0105民初12345号（年份直接跟法院代码）
    r'(\d{4})([^\d\s]{1}[^\s（）\(\)]{1,19}?)(\d+)号',
]


class InfoExtractor:
    """
    关键信息提取器
    
    使用 Ollama 大模型从法院文书中提取关键信息：
    - 传票：案号、开庭时间
    - 执行裁定书：案号、财产保全到期时间（预留扩展）
    
    Requirements: 4.3, 4.4
    """
    
    # 传票信息提取提示词
    SUMMONS_PROMPT = """请从以下传票内容中提取案号和开庭时间。

传票内容：
{text}

提取要求：
1. 案号格式：（年份）法院代码+案件类型字号+序号+号
   - 年份：4位数字，如2024、2025
   - 法院代码：省份简称+区县代码，如"粤0604"、"京0105"、"沪0115"
   - 案件类型字号（必须包含）：民初、民终、刑初、刑终、执、执保、执异、执恢、破、行初、行终等
   - 序号：数字
   - 必须以"号"字结尾
   - 示例：（2024）粤0604民初41257号、（2025）京0105刑初12345号
   
2. 重要：案号中必须包含案件类型字号（如民初、民终、刑初等），不能省略！
   - 错误示例：（2025）粤060441257（缺少案件类型）
   - 正确示例：（2025）粤0604民初41257号

3. 开庭时间需要包含完整的日期和时间，格式为：YYYY-MM-DD HH:MM

4. 如果无法确定某个字段，请返回 null

请严格按照以下 JSON 格式返回结果，不要包含其他内容：
{{"case_number": "案号或null", "court_time": "YYYY-MM-DD HH:MM或null"}}
"""
    
    # 执行裁定书信息提取提示词（预留扩展）
    EXECUTION_PROMPT = """请从以下执行裁定书中提取案号和财产保全到期时间。

裁定书内容：
{text}

提取要求：
1. 案号格式：（年份）法院代码+案件类型字号+序号+号
   - 年份：4位数字，如2024、2025
   - 法院代码：省份简称+区县代码，如"粤0604"、"京0105"
   - 案件类型字号（必须包含）：执、执保、执异、执恢、民初、民终等
   - 序号：数字
   - 必须以"号"字结尾
   - 示例：（2024）粤0604执保12345号、（2025）京0105执12345号
   
2. 重要：案号中必须包含案件类型字号，不能省略！

3. 财产保全到期时间格式为：YYYY-MM-DD

4. 如果无法确定某个字段，请返回 null

请严格按照以下 JSON 格式返回结果，不要包含其他内容：
{{"case_number": "案号或null", "preservation_deadline": "YYYY-MM-DD或null"}}
"""
    
    def __init__(
        self,
        ollama_model: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
    ):
        """
        初始化信息提取器
        
        Args:
            ollama_model: Ollama 模型名称，默认从配置读取
            ollama_base_url: Ollama 服务地址，默认从配置读取
        """
        self.ollama_model = ollama_model or get_ollama_model()
        self.ollama_base_url = ollama_base_url or get_ollama_base_url()
    
    # ==================== 正则表达式提取方法 ====================
    
    def _extract_case_number_by_regex(self, text: str) -> Optional[str]:
        """
        使用正则表达式从文本中提取案号
        
        优先提取标准格式的案号，支持中英文括号。
        
        Args:
            text: 文书文本
            
        Returns:
            提取到的案号（已标准化），未找到返回 None
        """
        if not text:
            return None
        
        for pattern in CASE_NUMBER_PATTERNS:
            matches = re.findall(pattern, text)
            if matches:
                # 取第一个匹配结果
                match = matches[0]
                if len(match) == 3:
                    year, court_type, seq = match
                    # 构建标准格式案号
                    case_number = f"（{year}）{court_type}{seq}号"
                    # 标准化处理
                    normalized = self._normalize_case_number(case_number)
                    logger.info(f"正则提取到案号: {normalized} (原始匹配: {match})")
                    return normalized
        
        logger.debug("正则未能提取到案号")
        return None
    
    def _extract_datetime_by_regex(self, text: str) -> List[Tuple[datetime, str, int]]:
        """
        使用正则表达式从文本中提取日期时间
        
        Args:
            text: 文书文本
            
        Returns:
            提取到的日期时间列表，每项为 (datetime对象, 原始匹配文本, 上下文得分)
        """
        results = []
        
        for pattern, has_am_pm in DATETIME_PATTERNS:
            for match in re.finditer(pattern, text):
                try:
                    groups = match.groups()
                    matched_text = match.group(0)
                    
                    # 解析年月日时分
                    if has_am_pm and len(groups) == 6:
                        # 带上午/下午格式：年、月、日、上午/下午、时、分
                        year = int(groups[0])
                        month = int(groups[1])
                        day = int(groups[2])
                        am_pm = groups[3]
                        hour = int(groups[4])
                        minute = int(groups[5])
                        
                        # 验证上午/下午标识
                        if am_pm not in ('上午', '下午'):
                            logger.debug(f"无效的上午/下午标识: {am_pm}, 跳过匹配: {matched_text}")
                            continue
                        
                        # 处理上午/下午
                        if am_pm == '下午' and hour < 12:
                            hour += 12
                        elif am_pm == '上午' and hour == 12:
                            hour = 0
                    elif len(groups) == 5:
                        # 标准格式：年、月、日、时、分
                        year = int(groups[0])
                        month = int(groups[1])
                        day = int(groups[2])
                        hour = int(groups[3])
                        minute = int(groups[4])
                    else:
                        logger.debug(f"未知的分组数量: {len(groups)}, 跳过匹配: {matched_text}")
                        continue
                    
                    # 验证日期时间有效性
                    if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
                        logger.debug(f"日期时间无效: {matched_text}")
                        continue
                    
                    # 验证年份合理性（2020-2030）
                    if not (2020 <= year <= 2030):
                        logger.debug(f"年份不合理: {year}, 跳过匹配: {matched_text}")
                        continue
                    
                    dt = datetime(year, month, day, hour, minute)
                    
                    # 计算上下文得分
                    context_score = self._calculate_context_score(text, match.start())
                    
                    # 避免重复添加相同时间
                    if not any(abs((dt - existing[0]).total_seconds()) < 60 for existing in results):
                        results.append((dt, matched_text, context_score))
                        logger.debug(f"正则提取到时间: {dt}, 原文: {matched_text}, 上下文得分: {context_score}")
                        
                except (ValueError, IndexError) as e:
                    logger.debug(f"解析日期时间失败: {match.group(0)}, 错误: {e}")
                    continue
        
        return results
    
    def _calculate_context_score(self, text: str, match_position: int) -> int:
        """
        计算匹配位置的上下文得分
        
        根据匹配位置附近是否有开庭相关关键词来计算得分。
        使用分层权重：高权重25分，中权重15分，低权重8分。
        
        Args:
            text: 完整文本
            match_position: 匹配位置
            
        Returns:
            上下文得分（0-100）
        """
        # 获取匹配位置前后的上下文（前100字符，后50字符）
        context_start = max(0, match_position - 100)
        context_end = min(len(text), match_position + 50)
        context = text[context_start:context_end]
        
        score = 0
        
        # 高权重关键词：25分
        for keyword in HEARING_HIGH_WEIGHT_KEYWORDS:
            if keyword in context:
                score += 25
        
        # 中权重关键词：15分
        for keyword in HEARING_MEDIUM_WEIGHT_KEYWORDS:
            if keyword in context:
                score += 15
        
        # 低权重关键词：8分
        for keyword in HEARING_LOW_WEIGHT_KEYWORDS:
            if keyword in context:
                score += 8
        
        # 最高100分
        return min(score, 100)
    
    def _validate_hearing_datetime(self, dt: datetime) -> Tuple[bool, int, str]:
        """
        校验开庭时间的合理性
        
        校验规则：
        1. 时间应该在未来或近期（不超过过去7天）
        2. 时间不应该超过未来2年
        3. 开庭时间通常在工作时间（8:00-18:00）
        4. 开庭时间通常不在周末（但法院有时也会安排）
        
        Args:
            dt: 待校验的时间
            
        Returns:
            (是否有效, 合理性得分0-100, 校验说明)
        """
        now = datetime.now()
        score = 50  # 基础分
        reasons = []
        
        # 1. 检查是否在合理的时间范围内
        days_diff = (dt.date() - now.date()).days
        
        if days_diff < -7:
            # 过去超过7天，可能是错误识别
            reasons.append(f"时间已过去{abs(days_diff)}天")
            score -= 30
        elif days_diff < 0:
            # 过去7天内，可能是刚过的开庭
            reasons.append(f"时间已过去{abs(days_diff)}天")
            score -= 10
        elif days_diff > 365 * 2:
            # 超过2年后，不太合理
            reasons.append(f"时间在{days_diff}天后，超过2年")
            score -= 40
        elif days_diff > 365:
            # 1-2年后，可能但不常见
            reasons.append(f"时间在{days_diff}天后")
            score -= 15
        elif days_diff > 180:
            # 半年到1年，较少见
            reasons.append(f"时间在{days_diff}天后")
            score -= 5
        else:
            # 未来半年内，最合理
            reasons.append(f"时间在{days_diff}天后")
            score += 20
        
        # 2. 检查是否在工作时间
        hour = dt.hour
        if 8 <= hour <= 18:
            # 正常工作时间
            score += 15
            reasons.append("工作时间内")
        elif 7 <= hour < 8 or 18 < hour <= 20:
            # 边缘时间，可能但不常见
            score += 5
            reasons.append("边缘工作时间")
        else:
            # 非工作时间，不太可能
            score -= 20
            reasons.append(f"非工作时间({hour}点)")
        
        # 3. 检查是否是周末
        weekday = dt.weekday()
        if weekday >= 5:  # 周六或周日
            score -= 10
            reasons.append("周末")
        else:
            score += 5
            reasons.append("工作日")
        
        # 4. 检查分钟是否合理（通常是整点或半点）
        minute = dt.minute
        if minute in [0, 30]:
            score += 10
            reasons.append("整点/半点")
        elif minute in [15, 45]:
            score += 5
            reasons.append("刻钟")
        
        # 确保分数在0-100范围内
        score = max(0, min(100, score))
        
        # 有效性判断：分数大于30认为有效
        is_valid = score > 30
        
        return is_valid, score, "; ".join(reasons)
    
    def _select_best_datetime(
        self, 
        regex_results: List[Tuple[datetime, str, int]], 
        ollama_datetime: Optional[datetime]
    ) -> Tuple[Optional[datetime], str]:
        """
        从正则提取结果和 Ollama 结果中选择最佳时间
        
        交叉校验机制：
        1. 对所有候选时间进行合理性校验
        2. 如果正则和 Ollama 结果一致（日期相同），使用该结果
        3. 如果不一致，综合考虑上下文得分和合理性得分
        4. 如果正则没有结果，使用 Ollama 结果（需通过合理性校验）
        
        Args:
            regex_results: 正则提取结果列表
            ollama_datetime: Ollama 提取的时间
            
        Returns:
            (最佳时间, 提取方法描述)
        """
        if not regex_results and not ollama_datetime:
            return None, "无法提取"
        
        # 对正则结果进行合理性校验和综合评分
        validated_regex_results = []
        for dt, matched_text, context_score in regex_results:
            is_valid, validity_score, validity_reason = self._validate_hearing_datetime(dt)
            # 综合得分 = 上下文得分 * 0.6 + 合理性得分 * 0.4
            combined_score = context_score * 0.6 + validity_score * 0.4
            validated_regex_results.append({
                'datetime': dt,
                'matched_text': matched_text,
                'context_score': context_score,
                'validity_score': validity_score,
                'validity_reason': validity_reason,
                'combined_score': combined_score,
                'is_valid': is_valid,
            })
            logger.debug(
                f"正则候选: {dt}, 上下文={context_score}, 合理性={validity_score}({validity_reason}), "
                f"综合={combined_score:.1f}, 有效={is_valid}"
            )
        
        # 过滤掉无效的结果，按综合得分排序
        valid_regex_results = [r for r in validated_regex_results if r['is_valid']]
        valid_regex_results.sort(key=lambda x: x['combined_score'], reverse=True)
        
        # 校验 Ollama 结果
        ollama_valid = False
        ollama_validity_score = 0
        ollama_validity_reason = ""
        if ollama_datetime:
            ollama_valid, ollama_validity_score, ollama_validity_reason = self._validate_hearing_datetime(ollama_datetime)
            logger.debug(
                f"Ollama候选: {ollama_datetime}, 合理性={ollama_validity_score}({ollama_validity_reason}), "
                f"有效={ollama_valid}"
            )
        
        # 情况1：只有 Ollama 结果
        if not valid_regex_results:
            if ollama_datetime and ollama_valid:
                logger.info(f"仅使用 Ollama 结果: {ollama_datetime} (合理性={ollama_validity_score})")
                return ollama_datetime, f"ollama(validity={ollama_validity_score})"
            elif ollama_datetime:
                # Ollama 结果不合理，但没有其他选择
                logger.warning(f"Ollama 结果合理性较低: {ollama_datetime} ({ollama_validity_reason})")
                return ollama_datetime, f"ollama(低合理性:{ollama_validity_reason})"
            else:
                # 检查是否有被过滤掉的正则结果
                if validated_regex_results:
                    best_invalid = max(validated_regex_results, key=lambda x: x['combined_score'])
                    logger.warning(
                        f"所有正则结果合理性较低，使用最佳候选: {best_invalid['datetime']} "
                        f"({best_invalid['validity_reason']})"
                    )
                    return best_invalid['datetime'], f"regex(低合理性:{best_invalid['validity_reason']})"
                return None, "无法提取"
        
        # 情况2：有有效的正则结果
        best_regex = valid_regex_results[0]
        best_regex_dt = best_regex['datetime']
        best_regex_combined = best_regex['combined_score']
        
        if not ollama_datetime or not ollama_valid:
            logger.info(
                f"使用正则结果: {best_regex_dt}, 综合得分={best_regex_combined:.1f} "
                f"(上下文={best_regex['context_score']}, 合理性={best_regex['validity_score']})"
            )
            return best_regex_dt, f"regex(score={best_regex_combined:.0f})"
        
        # 情况3：正则和 Ollama 都有有效结果，进行交叉校验
        date_diff = abs((best_regex_dt.date() - ollama_datetime.date()).days)
        time_diff = abs((best_regex_dt - ollama_datetime).total_seconds())
        
        if date_diff == 0 and time_diff < 3600:  # 同一天且时间差小于1小时
            # 结果一致，使用正则结果（更精确）
            logger.info(f"正则和Ollama结果一致: {best_regex_dt}")
            return best_regex_dt, "regex+ollama(一致)"
        
        if date_diff == 0:
            # 日期一致但时间不同
            logger.warning(
                f"时间冲突: 正则={best_regex_dt}, Ollama={ollama_datetime}, "
                f"时间差={time_diff}秒"
            )
            # 日期相同时，优先使用正则结果（从原文直接提取，更可靠）
            # 只有当正则得分很低时才考虑 Ollama
            if best_regex_combined >= 40:
                return best_regex_dt, f"regex(score={best_regex_combined:.0f},时间冲突)"
            else:
                # 正则得分太低，使用 Ollama
                return ollama_datetime, f"ollama(validity={ollama_validity_score},时间冲突,正则得分低)"
        
        # 日期不一致
        logger.warning(
            f"日期冲突: 正则={best_regex_dt.date()}, Ollama={ollama_datetime.date()}, "
            f"差异={date_diff}天"
        )
        
        # 检查是否有其他正则结果与 Ollama 一致
        for result in valid_regex_results[1:]:
            if abs((result['datetime'].date() - ollama_datetime.date()).days) == 0:
                logger.info(f"找到与Ollama一致的备选正则结果: {result['datetime']}")
                return result['datetime'], f"regex(score={result['combined_score']:.0f},与ollama一致)"
        
        # 比较最佳正则和 Ollama 的得分
        if best_regex_combined >= 60:
            return best_regex_dt, f"regex(score={best_regex_combined:.0f},日期冲突)"
        elif ollama_validity_score >= 50:
            return ollama_datetime, f"ollama(validity={ollama_validity_score},日期冲突)"
        else:
            # 都不太可靠，选择综合得分更高的
            if best_regex_combined >= ollama_validity_score:
                return best_regex_dt, f"regex(score={best_regex_combined:.0f},低置信度)"
            else:
                return ollama_datetime, f"ollama(validity={ollama_validity_score},低置信度)"
    
    def extract_summons_info(self, text: str) -> Dict[str, Any]:
        """
        提取传票信息
        
        从传票文本中提取案号和开庭时间。
        案号提取：优先使用正则表达式，失败再用 Ollama。
        开庭时间：使用正则表达式和 Ollama 双重提取，并进行交叉校验。
        
        Args:
            text: 传票文本内容
            
        Returns:
            Dict[str, Any]: 包含以下字段的字典：
                - case_number: 案号，提取失败时为 None
                - court_time: 开庭时间（datetime），提取失败时为 None
                - extraction_method: 时间提取方法描述
                
        Raises:
            ServiceUnavailableError: Ollama 服务不可用
            RecognitionTimeoutError: 提取超时
            RuntimeError: 提取过程中发生其他错误
            
        Requirements: 4.3
        """
        if not text or not text.strip():
            logger.warning(
                "传票内容为空，无法提取信息",
                extra={"action": "extract_summons_info", "result": "empty_text"}
            )
            return {"case_number": None, "court_time": None, "extraction_method": None}
        
        # 截取文本前 4000 字符
        truncated_text = text[:4000] if len(text) > 4000 else text
        
        logger.info(
            f"开始提取传票信息",
            extra={
                "action": "extract_summons_info",
                "text_length": len(text),
                "truncated_length": len(truncated_text)
            }
        )
        
        # 1. 先用正则表达式提取案号（优先）
        regex_case_number = self._extract_case_number_by_regex(truncated_text)
        if regex_case_number:
            logger.info(f"正则成功提取案号: {regex_case_number}")
        
        # 2. 用正则表达式提取时间
        regex_datetimes = self._extract_datetime_by_regex(truncated_text)
        logger.info(f"正则提取到 {len(regex_datetimes)} 个时间候选")
        for dt, matched_text, score in regex_datetimes:
            logger.info(f"  - {dt} (原文: {matched_text}, 得分: {score})")
        
        # 3. 调用 Ollama 提取（案号仅在正则失败时使用）
        ollama_result = {"case_number": None, "court_time": None}
        ollama_datetime = None
        need_ollama_case_number = regex_case_number is None
        
        try:
            # 构建消息
            prompt = self.SUMMONS_PROMPT.format(text=truncated_text)
            messages = [{"role": "user", "content": prompt}]
            
            # 调用 Ollama
            response = chat(
                model=self.ollama_model,
                messages=messages,
                base_url=self.ollama_base_url,
            )
            
            # 解析响应
            ollama_result = self._parse_summons_response(response)
            ollama_datetime = ollama_result.get("court_time")
            
            if ollama_datetime:
                logger.info(f"Ollama 提取到时间: {ollama_datetime}")
            
            if need_ollama_case_number and ollama_result.get("case_number"):
                logger.info(f"Ollama 提取到案号: {ollama_result.get('case_number')}")
            
        except ConnectionError as e:
            logger.warning(f"Ollama 服务不可用，将仅使用正则结果: {e}")
        except TimeoutError as e:
            logger.warning(f"Ollama 提取超时，将仅使用正则结果: {e}")
        except Exception as e:
            logger.warning(f"Ollama 提取失败，将仅使用正则结果: {e}")
        
        # 4. 交叉校验，选择最佳时间
        best_datetime, extraction_method = self._select_best_datetime(regex_datetimes, ollama_datetime)
        logger.info(f"最终选择时间: {best_datetime}, 方法: {extraction_method}")
        
        # 5. 确定最终案号（正则优先）
        final_case_number = regex_case_number if regex_case_number else ollama_result.get("case_number")
        case_number_source = "regex" if regex_case_number else ("ollama" if ollama_result.get("case_number") else None)
        
        # 6. 构建最终结果
        result = {
            "case_number": final_case_number,
            "court_time": best_datetime,
            "extraction_method": extraction_method,
        }
        
        logger.info(
            f"传票信息提取完成",
            extra={
                "action": "extract_summons_info",
                "case_number": result.get('case_number'),
                "case_number_source": case_number_source,
                "court_time": str(result.get('court_time')) if result.get('court_time') else None,
                "extraction_method": extraction_method
            }
        )
        return result
    
    def extract_execution_info(self, text: str) -> Dict[str, Any]:
        """
        提取执行裁定书信息（预留扩展）
        
        从执行裁定书文本中提取案号和财产保全到期时间。
        
        Args:
            text: 执行裁定书文本内容
            
        Returns:
            Dict[str, Any]: 包含以下字段的字典：
                - case_number: 案号，提取失败时为 None
                - preservation_deadline: 保全到期时间（datetime），提取失败时为 None
                
        Raises:
            ServiceUnavailableError: Ollama 服务不可用
            RecognitionTimeoutError: 提取超时
            RuntimeError: 提取过程中发生其他错误
            
        Requirements: 4.4
        """
        if not text or not text.strip():
            logger.warning(
                "执行裁定书内容为空，无法提取信息",
                extra={"action": "extract_execution_info", "result": "empty_text"}
            )
            return {"case_number": None, "preservation_deadline": None}
        
        # 截取文本前 4000 字符
        truncated_text = text[:4000] if len(text) > 4000 else text
        
        logger.info(
            f"开始提取执行裁定书信息",
            extra={
                "action": "extract_execution_info",
                "text_length": len(text),
                "truncated_length": len(truncated_text)
            }
        )
        
        try:
            # 构建消息
            prompt = self.EXECUTION_PROMPT.format(text=truncated_text)
            messages = [{"role": "user", "content": prompt}]
            
            # 调用 Ollama
            response = chat(
                model=self.ollama_model,
                messages=messages,
                base_url=self.ollama_base_url,
            )
            
            # 解析响应
            result = self._parse_execution_response(response)
            
            logger.info(
                f"执行裁定书信息提取完成",
                extra={
                    "action": "extract_execution_info",
                    "case_number": result.get('case_number'),
                    "preservation_deadline": str(result.get('preservation_deadline')) if result.get('preservation_deadline') else None
                }
            )
            return result
            
        except ConnectionError as e:
            logger.error(
                f"Ollama 服务不可用: {e}",
                extra={
                    "action": "extract_execution_info",
                    "error_type": "connection_error",
                    "error": str(e)
                }
            )
            raise ServiceUnavailableError(
                message="AI 服务暂时不可用，请稍后重试",
                code="OLLAMA_SERVICE_UNAVAILABLE",
                errors={"service": "Ollama 服务连接失败"},
                service_name="Ollama"
            )
        except TimeoutError as e:
            logger.error(
                f"执行裁定书信息提取超时: {e}",
                extra={
                    "action": "extract_execution_info",
                    "error_type": "timeout_error",
                    "error": str(e)
                }
            )
            raise RecognitionTimeoutError(
                message="信息提取超时，请重试",
                code="EXTRACTION_TIMEOUT",
                errors={"timeout": "AI 提取超时"}
            )
        except Exception as e:
            logger.error(
                f"执行裁定书信息提取失败: {str(e)}",
                extra={
                    "action": "extract_execution_info",
                    "error_type": type(e).__name__,
                    "error": str(e)
                },
                exc_info=True
            )
            raise RuntimeError(f"执行裁定书信息提取失败: {str(e)}")
    
    def _parse_summons_response(self, response: dict) -> Dict[str, Any]:
        """
        解析传票信息提取响应
        
        Args:
            response: Ollama API 响应
            
        Returns:
            Dict[str, Any]: 提取的信息
        """
        result = {"case_number": None, "court_time": None}
        
        try:
            # 提取响应内容
            if "message" not in response or "content" not in response["message"]:
                logger.warning("Ollama 响应格式异常")
                return result
            
            content = response["message"]["content"]
            
            # 尝试解析 JSON
            parsed = self._extract_json_from_response(content)
            
            if parsed is None:
                logger.warning(f"无法从响应中提取 JSON: {content[:200]}")
                return result
            
            # 提取案号
            case_number = parsed.get("case_number")
            if case_number and case_number.lower() != "null":
                result["case_number"] = self._normalize_case_number(case_number)
            
            # 提取开庭时间
            court_time = parsed.get("court_time")
            if court_time and court_time.lower() != "null":
                result["court_time"] = self._parse_datetime(court_time)
            
            return result
            
        except Exception as e:
            logger.warning(f"解析传票响应失败: {str(e)}")
            return result
    
    def _parse_execution_response(self, response: dict) -> Dict[str, Any]:
        """
        解析执行裁定书信息提取响应
        
        Args:
            response: Ollama API 响应
            
        Returns:
            Dict[str, Any]: 提取的信息
        """
        result = {"case_number": None, "preservation_deadline": None}
        
        try:
            # 提取响应内容
            if "message" not in response or "content" not in response["message"]:
                logger.warning("Ollama 响应格式异常")
                return result
            
            content = response["message"]["content"]
            
            # 尝试解析 JSON
            parsed = self._extract_json_from_response(content)
            
            if parsed is None:
                logger.warning(f"无法从响应中提取 JSON: {content[:200]}")
                return result
            
            # 提取案号
            case_number = parsed.get("case_number")
            if case_number and case_number.lower() != "null":
                result["case_number"] = self._normalize_case_number(case_number)
            
            # 提取保全到期时间
            deadline = parsed.get("preservation_deadline")
            if deadline and deadline.lower() != "null":
                result["preservation_deadline"] = self._parse_date(deadline)
            
            return result
            
        except Exception as e:
            logger.warning(f"解析执行裁定书响应失败: {str(e)}")
            return result
    
    def _extract_json_from_response(self, content: str) -> Optional[dict]:
        """
        从响应内容中提取 JSON
        
        支持处理包含额外文本的响应。
        
        Args:
            content: 响应内容
            
        Returns:
            Optional[dict]: 解析出的 JSON 对象，失败返回 None
        """
        content = content.strip()
        
        # 直接尝试解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # 尝试提取 JSON 块
        start_idx = content.find("{")
        end_idx = content.rfind("}")
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = content[start_idx:end_idx + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        # 尝试处理 markdown 代码块
        if "```json" in content:
            try:
                json_start = content.index("```json") + 7
                json_end = content.index("```", json_start)
                json_str = content[json_start:json_end].strip()
                return json.loads(json_str)
            except (ValueError, json.JSONDecodeError):
                pass
        
        if "```" in content:
            try:
                json_start = content.index("```") + 3
                json_end = content.index("```", json_start)
                json_str = content[json_start:json_end].strip()
                return json.loads(json_str)
            except (ValueError, json.JSONDecodeError):
                pass
        
        return None
    
    def _normalize_case_number(self, case_number: str) -> str:
        """
        标准化案号格式
        
        处理常见的案号格式变体，统一为标准格式。
        例如：2025粤0604民初41257号 -> （2025）粤0604民初41257号
        
        Args:
            case_number: 原始案号字符串
            
        Returns:
            str: 标准化后的案号
        """
        if not case_number:
            return case_number
        
        # 去除首尾空白
        case_number = case_number.strip()
        
        # 将全角括号转换为半角（统一处理）
        case_number = case_number.replace("（", "(").replace("）", ")")
        
        # 检查是否缺少括号：以年份开头但没有括号
        # 匹配格式：2025粤0604民初41257号（年份后直接跟法院代码）
        no_bracket_pattern = r'^(\d{4})([^\d\(\)])'
        match = re.match(no_bracket_pattern, case_number)
        if match:
            # 年份后没有括号，需要补全
            year = match.group(1)
            rest = case_number[4:]
            case_number = f"({year}){rest}"
        
        # 将半角括号转换为中文括号（标准格式）
        case_number = case_number.replace("(", "（").replace(")", "）")
        
        return case_number
    
    def _parse_datetime(self, datetime_str: str) -> Optional[datetime]:
        """
        解析日期时间字符串
        
        支持多种常见格式。
        
        Args:
            datetime_str: 日期时间字符串
            
        Returns:
            Optional[datetime]: 解析后的 datetime 对象，失败返回 None
        """
        if not datetime_str:
            return None
        
        datetime_str = datetime_str.strip()
        
        # 支持的日期时间格式
        formats = [
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y年%m月%d日 %H:%M",
            "%Y年%m月%d日 %H时%M分",
            "%Y年%m月%d日%H时%M分",
            "%Y/%m/%d %H:%M",
            "%Y.%m.%d %H:%M",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(datetime_str, fmt)
            except ValueError:
                continue
        
        # 尝试使用正则表达式提取
        # 匹配中文格式：2026年1月5日9时30分（空格删除后的格式）
        # 注意：日后面可能没有空格，直接跟小时数字
        pattern_cn = r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})时(\d{1,2})分?"
        match = re.search(pattern_cn, datetime_str)
        if match:
            try:
                year, month, day, hour, minute = map(int, match.groups())
                return datetime(year, month, day, hour, minute)
            except ValueError:
                pass
        
        # 匹配标准格式：YYYY-MM-DD HH:MM 或类似格式
        pattern_std = r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\s+(\d{1,2}):(\d{1,2})"
        match = re.search(pattern_std, datetime_str)
        if match:
            try:
                year, month, day, hour, minute = map(int, match.groups())
                return datetime(year, month, day, hour, minute)
            except ValueError:
                pass
        
        logger.warning(f"无法解析日期时间: {datetime_str}")
        return None
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        解析日期字符串
        
        支持多种常见格式。
        
        Args:
            date_str: 日期字符串
            
        Returns:
            Optional[datetime]: 解析后的 datetime 对象（时间部分为 00:00:00），失败返回 None
        """
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # 支持的日期格式
        formats = [
            "%Y-%m-%d",
            "%Y年%m月%d日",
            "%Y/%m/%d",
            "%Y.%m.%d",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # 尝试使用正则表达式提取
        pattern = r"(\d{4})[-年/.](\d{1,2})[-月/.](\d{1,2})"
        match = re.search(pattern, date_str)
        if match:
            try:
                year, month, day = map(int, match.groups())
                return datetime(year, month, day)
            except ValueError:
                pass
        
        logger.warning(f"无法解析日期: {date_str}")
        return None
