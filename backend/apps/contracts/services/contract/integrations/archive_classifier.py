"""归档分类器 - 文件夹扫描场景下的归档清单项匹配和工作日志建议。

根据文件名/文件夹路径关键词将扫描到的 PDF/docx 匹配到归档清单项，
并从日期前缀子目录名（YYYY.MM.DD-事项名）生成律师工作日志建议。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from apps.contracts.services.archive.category_mapping import get_archive_category
from apps.contracts.services.archive.constants import ARCHIVE_CHECKLIST

logger = logging.getLogger(__name__)

# ============================================================
# 学习规则加载（代码文件中的规则，模块级缓存）
# ============================================================
try:
    from ._learned_rules import LEARNED_FILENAME_KEYWORD_TO_ARCHIVE_CODE as _LEARNED_CODE_RULES
except ImportError:
    _LEARNED_CODE_RULES: dict[str, dict[str, list[str]]] = {}


def reload_learned_code_rules() -> None:
    """重新加载代码文件中的学习规则（导出后调用）。"""
    global _LEARNED_CODE_RULES
    try:
        import importlib
        from . import _learned_rules as _rules_module

        importlib.reload(_rules_module)
        _LEARNED_CODE_RULES = _rules_module.LEARNED_FILENAME_KEYWORD_TO_ARCHIVE_CODE
        logger.info(
            "learned_code_rules_reloaded",
            extra={"rule_count": sum(len(kws) for d in _LEARNED_CODE_RULES.values() for kws in d.values())},
        )
    except (ImportError, OSError):
        _LEARNED_CODE_RULES = {}

# ============================================================
# 跳过规则 - 以下关键词命中的文件不导入
# ============================================================
_SKIP_KEYWORDS: tuple[str, ...] = (
    "退费账户确认书",
    "退费账户",
    "收款确认书",
    "收取执行款",
    "拍卖通知",
    "分配方案",
    "顺丰单",
    "快递单",
    "诉讼材料接收表",
    "送达地址确认书",
    "诉讼费退费",
    "退费申请",
    "工作联系函",
    "开户许可证",
    "银行卡",
)

# ============================================================
# 文件夹路径关键词 → archive_item_code 映射
# ============================================================
# 匹配时，对归档分类对应的清单项中 source="case" 的条目进行关键词匹配。
# 优先匹配更具体的（列表靠前的优先），命中即返回。
# ============================================================
_FOLDER_KEYWORD_TO_ARCHIVE_CODE: dict[str, dict[str, list[str]]] = {
    # non_litigation
    "non_litigation": {
        "nl_12": ["授权委托", "委托授权"],
        "nl_8": ["律师函", "法律意见"],
        "nl_9": ["修订版", "批注版", "律师修订"],
    },
    # litigation
    "litigation": {
        "lt_20": ["授权委托", "委托授权"],
        "lt_7": ["起诉状", "起诉书", "上诉状", "上诉书", "答辩状", "答辩书", "执行申请"],
        "lt_8": ["阅卷"],
        "lt_9": ["会见当事人", "会见笔录", "谈话笔录", "询问笔录"],
        "lt_11": ["财产保全", "诉讼保全", "证据保全", "先行给付", "限制高消费", "取保候审", "查封清单", "缴费通知", "诉前调解告知", "受理通知", "交费通知", "交费清单"],
        "lt_14": ["开庭通知", "出庭通知", "传票"],
        "lt_15": ["代理词", "代理意见"],
        "lt_12": ["承办意见", "内部意见", "律师意见", "辩护意见"],
        "lt_13": ["集体讨论", "讨论记录"],
        "lt_16": ["庭审笔录", "开庭笔录", "审理笔录"],
        "lt_17": ["判决书", "裁定书", "调解书", "终本裁定", "执行裁定", "查封裁定"],
        "lt_10": ["调查", "取证", "追加第三人", "网络查控", "催促执行", "中止执行", "申请律师调查令"],
    },
    # criminal
    "criminal": {
        "cr_18": ["授权委托", "委托授权"],
        "cr_12": ["辩护词", "辩护意见", "代理词", "代理意见"],
        "cr_7": ["会见笔录", "会见被告人"],
        "cr_8": ["调查", "取证", "取保候审"],
        "cr_11": ["起诉书", "起诉状", "上诉状", "上诉书", "不起诉申请"],
        "cr_9": ["承办意见", "内部意见"],
        "cr_10": ["集体讨论", "讨论记录"],
        "cr_13": ["开庭通知", "出庭通知", "传票"],
        "cr_14": ["裁定书", "判决书", "判决"],
        "cr_15": ["上诉书", "抗诉书"],
    },
}

# ============================================================
# 文件名关键词 → archive_item_code 映射
# ============================================================
_FILENAME_KEYWORD_TO_ARCHIVE_CODE: dict[str, dict[str, list[str]]] = {
    "non_litigation": {
        "nl_12": ["授权委托书", "授权", "所函", "律师证"],
        "nl_7": ["委托人提供", "当事人提供", "我方材料"],
        "nl_8": ["律师函", "法律意见书"],
        "nl_9": ["修订版", "批注版", "律师修订", "证据清单", "证据明细", "材料清单"],
    },
    "litigation": {
        "lt_20": ["授权委托书", "授权", "所函", "律师证", "身份证", "营业执照", "法定代表人"],
        "lt_7": ["起诉状", "起诉书", "上诉状", "上诉书", "答辩状", "答辩书", "执行申请书", "强制执行申请书", "续封申请"],
        "lt_8": ["阅卷笔录", "阅卷"],
        "lt_9": ["会见笔录", "会见当事人", "谈话笔录", "询问笔录"],
        "lt_10": ["证据清单", "证据明细", "材料清单", "追加第三人", "网络查控", "催促执行", "中止执行", "调查令"],
        "lt_11": ["财产保全", "诉讼保全", "证据保全", "限制高消费", "取保候审", "续封申请", "查封清单", "缴费通知", "诉前调解告知书", "受理通知书", "交费通知", "交费清单"],
        "lt_14": ["传票", "开庭通知", "出庭通知"],
        "lt_15": ["代理词"],
        "lt_12": ["辩护意见", "律师意见", "承办意见"],
        "lt_16": ["庭审笔录", "开庭笔录", "审理笔录", "调解笔录"],
        "lt_17": ["判决书", "裁定书", "调解书", "终本裁定", "执行裁定", "查封裁定", "解除查封"],
    },
    "criminal": {
        "cr_18": ["授权委托书", "授权", "所函", "律师证", "身份证", "户口本"],
        "cr_7": ["会见笔录", "会见被告人"],
        "cr_8": ["取保候审", "证据清单", "证据明细", "材料清单"],
        "cr_11": ["起诉书", "起诉状", "不起诉申请"],
        "cr_12": ["辩护词", "辩护意见", "代理词"],
        "cr_13": ["传票", "开庭通知", "出庭通知"],
        "cr_14": ["判决书", "裁定书", "刑事判决"],
        "cr_15": ["上诉书", "抗诉书"],
    },
}

# ============================================================
# 证据材料文件夹关键词
# ============================================================
_EVIDENCE_FOLDER_KEYWORDS: tuple[str, ...] = ("主要证据材料", "证据材料", "证据目录")

# 证据文件夹下仅导入含以下关键词的文件
_EVIDENCE_FILENAME_KEYWORDS: tuple[str, ...] = ("证据明细", "证据清单")

# ============================================================
# 工作日志 - 动词补全
# ============================================================
# 已有动词列表（原文包含这些则不补全）
_EXISTING_VERBS: tuple[str, ...] = (
    "收到", "提交", "邮寄", "签名", "申请", "评估", "办理", "补交", "领取",
    "签收", "发送", "签署", "审核", "审查", "出具", "收到", "领取",
)

# 非诉（常法）默认动词
_NL_DEFAULT_VERB = "审核"

# 诉讼/刑事 - 语境推断（事项名 → 动词）
# 不在此映射中的事项名，默认补"提交"
_LITIGATION_VERB_MAP: dict[str, str] = {
    "开庭通知": "收到",
    "传票": "收到",
    "判决书": "收到",
    "裁定书": "收到",
    "调解书": "收到",
    "终本": "收到",
    "终本裁定": "收到",
    "执行裁定": "收到",
    "查封": "收到",
    "解封": "收到",
    "立案通知": "收到",
    "交费通知": "收到",
    "开庭": "参加",
    "调解": "参加",
}

# 日期前缀子目录名正则
_DATE_FOLDER_PATTERN = re.compile(r"^(\d{4})[.\-](\d{2})[.\-](\d{2})\s*[-—\s]\s*(.+)$")


def classify_archive_material(
    *,
    filename: str,
    source_path: str,
    archive_category: str,
) -> dict[str, Any]:
    """将扫描到的文件匹配到归档清单项。

    Args:
        filename: 文件名（含扩展名）
        source_path: 文件完整路径
        archive_category: 归档分类（non_litigation / litigation / criminal）

    Returns:
        匹配结果字典，包含：
        - archive_item_code: 归档清单项编号，空字符串表示未匹配
        - archive_item_name: 归档清单项名称
        - category: MaterialCategory 值（case_material 或 skip）
        - confidence: 匹配置信度
        - reason: 匹配原因
        - is_evidence_folder: 是否在证据材料文件夹中
    """
    normalized_filename = _normalize_for_match(filename)
    normalized_path = _normalize_for_match(source_path)

    # 1. 跳过规则
    for skip_kw in _SKIP_KEYWORDS:
        if _normalize_for_match(skip_kw) in normalized_filename:
            return {
                "archive_item_code": "",
                "archive_item_name": "跳过",
                "category": "skip",
                "confidence": 1.0,
                "reason": f"跳过规则命中：{skip_kw}",
                "is_evidence_folder": False,
            }

    # 2. 证据材料文件夹特殊筛选
    is_evidence_folder = any(_normalize_for_match(kw) in normalized_path for kw in _EVIDENCE_FOLDER_KEYWORDS)
    if is_evidence_folder:
        has_evidence_keyword = any(_normalize_for_match(kw) in normalized_filename for kw in _EVIDENCE_FILENAME_KEYWORDS)
        if not has_evidence_keyword:
            return {
                "archive_item_code": "",
                "archive_item_name": "跳过（证据材料仅导入证据清单/明细）",
                "category": "skip",
                "confidence": 1.0,
                "reason": "证据文件夹下非证据清单/明细文件，跳过",
                "is_evidence_folder": True,
            }
        # 证据清单/明细 → lt_10 / cr_8
        evidence_code = _get_evidence_code(archive_category)
        evidence_name = _get_item_name(archive_category, evidence_code)
        return {
            "archive_item_code": evidence_code,
            "archive_item_name": evidence_name,
            "category": "case_material",
            "confidence": 0.95,
            "reason": "证据文件夹下证据清单/明细文件",
            "is_evidence_folder": True,
        }

    # 3. 学习规则匹配（优先级高于硬编码规则）
    learned_result = _match_by_learned_rules(normalized_filename, archive_category)
    if learned_result:
        return {
            **learned_result,
            "is_evidence_folder": False,
        }

    # 4. 文件夹路径关键词匹配
    folder_result = _match_by_folder_keywords(normalized_path, archive_category)
    if folder_result:
        return {
            **folder_result,
            "is_evidence_folder": False,
        }

    # 5. 文件名关键词匹配
    filename_result = _match_by_filename_keywords(normalized_filename, archive_category)
    if filename_result:
        return {
            **filename_result,
            "is_evidence_folder": False,
        }

    # 6. 未匹配
    return {
        "archive_item_code": "",
        "archive_item_name": "未匹配",
        "category": "case_material",
        "confidence": 0.0,
        "reason": "未命中关键词规则，请手动选择归档清单项",
        "is_evidence_folder": False,
    }


def parse_work_log_from_folder_name(
    folder_name: str,
    archive_category: str,
) -> dict[str, str] | None:
    """从日期前缀子目录名解析工作日志建议。

    Args:
        folder_name: 子目录名，如 "2024.09.11-立案"
        archive_category: 归档分类

    Returns:
        {"date": "2024-09-11", "content": "提交立案"} 或 None
    """
    match = _DATE_FOLDER_PATTERN.match(folder_name.strip())
    if not match:
        return None

    year, month, day, subject = match.group(1), match.group(2), match.group(3), match.group(4).strip()
    if not subject:
        return None

    date_str = f"{year}-{month}-{day}"
    content = _add_verb(subject, archive_category)

    return {"date": date_str, "content": content}


def collect_work_log_suggestions(scan_folder: str, archive_category: str) -> list[dict[str, str]]:
    """扫描目录下所有日期前缀子目录，返回工作日志建议列表。

    Args:
        scan_folder: 扫描根目录路径
        archive_category: 归档分类

    Returns:
        工作日志建议列表，按日期排序
    """
    root = Path(scan_folder).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return []

    suggestions: list[dict[str, str]] = []
    for child in root.rglob("*"):
        if not child.is_dir():
            continue
        result = parse_work_log_from_folder_name(child.name, archive_category)
        if result:
            suggestions.append(result)

    # 按日期排序
    suggestions.sort(key=lambda x: x["date"])
    return suggestions


def collect_archive_item_options(archive_category: str) -> list[dict[str, str]]:
    """获取归档清单项选项列表（source="case" 的条目）。

    Args:
        archive_category: 归档分类

    Returns:
        [{"code": "lt_7", "name": "起诉书、上诉书或答辩书"}, ...]
    """
    checklist = ARCHIVE_CHECKLIST.get(archive_category, [])
    return [
        {"code": item["code"], "name": item["name"]}
        for item in checklist
        if item.get("source") == "case"
    ]


# ============================================================
# 内部辅助函数
# ============================================================


def _match_by_learned_rules(
    normalized_filename: str,
    archive_category: str,
) -> dict[str, Any] | None:
    """学习规则匹配（先查代码文件规则，再查DB规则）。"""
    # 1. 代码文件中的学习规则（模块级缓存，无DB查询）
    code_mapping = _LEARNED_CODE_RULES.get(archive_category, {})
    for code, keywords in code_mapping.items():
        for keyword in keywords:
            if _normalize_for_match(keyword) in normalized_filename:
                name = _get_item_name(archive_category, code)
                return {
                    "archive_item_code": code,
                    "archive_item_name": name,
                    "category": "case_material",
                    "confidence": 0.95,
                    "reason": f"学习规则命中：{keyword}",
                }

    # 2. DB 中的学习规则
    db_result = _match_by_db_learned_rules(normalized_filename, archive_category)
    if db_result:
        return db_result

    return None


def _match_by_db_learned_rules(
    normalized_filename: str,
    archive_category: str,
) -> dict[str, Any] | None:
    """从 DB 查询学习规则匹配。"""
    try:
        from apps.contracts.models import ArchiveClassificationRule

        rules = ArchiveClassificationRule.objects.filter(
            archive_category=archive_category,
        ).values_list("filename_keyword", "archive_item_code")

        for keyword, code in rules:
            if _normalize_for_match(keyword) in normalized_filename:
                name = _get_item_name(archive_category, code)
                return {
                    "archive_item_code": code,
                    "archive_item_name": name,
                    "category": "case_material",
                    "confidence": 0.93,
                    "reason": f"学习规则(DB)命中：{keyword}",
                }
    except (OSError, RuntimeError):
        logger.exception("learned_rules_db_query_failed")

    return None


def _normalize_for_match(text: str) -> str:
    """标准化文本用于模糊匹配：去空格、转小写。"""
    value = str(text or "").strip().lower()
    if not value:
        return ""
    value = value.replace("\\", "/")
    value = re.sub(r"\s+", "", value)
    return value


def _match_by_folder_keywords(
    normalized_path: str,
    archive_category: str,
) -> dict[str, Any] | None:
    """文件夹路径关键词匹配。"""
    mapping = _FOLDER_KEYWORD_TO_ARCHIVE_CODE.get(archive_category, {})
    for code, keywords in mapping.items():
        for keyword in keywords:
            if _normalize_for_match(keyword) in normalized_path:
                name = _get_item_name(archive_category, code)
                return {
                    "archive_item_code": code,
                    "archive_item_name": name,
                    "category": "case_material",
                    "confidence": 0.92,
                    "reason": f"文件夹路径关键词命中：{keyword}",
                }
    return None


def _match_by_filename_keywords(
    normalized_filename: str,
    archive_category: str,
) -> dict[str, Any] | None:
    """文件名关键词匹配。"""
    mapping = _FILENAME_KEYWORD_TO_ARCHIVE_CODE.get(archive_category, {})
    for code, keywords in mapping.items():
        for keyword in keywords:
            if _normalize_for_match(keyword) in normalized_filename:
                name = _get_item_name(archive_category, code)
                return {
                    "archive_item_code": code,
                    "archive_item_name": name,
                    "category": "case_material",
                    "confidence": 0.90,
                    "reason": f"文件名关键词命中：{keyword}",
                }
    return None


def _get_item_name(archive_category: str, code: str) -> str:
    """根据归档分类和编号获取清单项名称。"""
    checklist = ARCHIVE_CHECKLIST.get(archive_category, [])
    for item in checklist:
        if item["code"] == code:
            return item["name"]
    return code


def _get_evidence_code(archive_category: str) -> str:
    """获取证据材料对应的 archive_item_code。"""
    mapping = {
        "non_litigation": "nl_9",
        "litigation": "lt_10",
        "criminal": "cr_8",
    }
    return mapping.get(archive_category, "lt_10")


def _add_verb(subject: str, archive_category: str) -> str:
    """为工作日志事项补全动词。

    - 非诉：补"审核"
    - 诉讼/刑事：根据语境补"提交"/"收到"
    - 原文已有动词则不补
    """
    # 检查原文是否已有动词
    for verb in _EXISTING_VERBS:
        if subject.startswith(verb):
            return subject

    # 非诉补"审核"
    if archive_category == "non_litigation":
        return f"{_NL_DEFAULT_VERB}{subject}"

    # 诉讼/刑事：语境推断
    for key, verb in _LITIGATION_VERB_MAP.items():
        if key in subject:
            return f"{verb}{subject}"

    # 默认补"提交"
    return f"提交{subject}"
