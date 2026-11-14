"""法院送达文书里的「模板类」过滤（送识别前排除）。

法院一次送达常附带 9~12 份文书，其中相当一部分是法院的固定模板：内容按案件填空，
**从不包含任何期限**（没有开庭时间、没有上诉期、没有保全到期日）。把它们送去识别
只是白烧一次 LLM 调用和时间，识别结果必然是「未识别到关键日期」。

口径（业务确认 2026-11-14）：
- **默认全部识别**，只排除明确无期限的模板；
- 廉政监督卡、送达地址确认书、退费申请书是点名的三类；
- 同类的固定表单（诉讼权利义务告知书、风险提示书、格式告知书等）一并排除。

**保守原则**：宁可多送一份（浪费一次 LLM），也不要把可能含期限的文书漏掉。
因此本清单按**文书类型名精确匹配**，不做模糊的词包含匹配——像「告知书」这种名字
既可能是模板（诉讼权利义务告知书），也可能是含保全到期日的实体文书（财产保全告知书），
不能用通配词一刀切。实体类文书（判决书/裁定书/传票/举证通知/交费通知…）永远不在此列。
"""

from __future__ import annotations

import re

# 文件名里出现即视为模板（按中文文书类型名匹配，大小写/空格/下划线无关）
_TEMPLATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # —— 业务点名的三类 ——
    re.compile(r"廉政监督卡"),
    re.compile(r"送达地址确认书"),
    re.compile(r"退费申请书"),
    # —— 同类固定表单（无期限）——
    re.compile(r"诉讼权利义务告知书"),
    re.compile(r"民事诉讼风险提示书"),
    re.compile(r"风险提示书"),
    re.compile(r"当事人送达地址确认"),
    re.compile(r"授权委托书"),  # 当事人自己提交的格式文书，被随案送达时同样无期限
    re.compile(r"案件流程告知书"),
    re.compile(r"审判流程告知书"),
    re.compile(r"廉政监督"),
    re.compile(r"司法作风监督卡"),
    re.compile(r"满意度评价表"),
    re.compile(r"回访表"),
)


def is_template_document(filename: str) -> bool:
    """文件名是否是「无期限的模板类文书」。

    Args:
        filename: 文书显示名（通常形如「廉政监督卡（张某诉李某案）_20261106收.pdf」）

    Returns:
        True 表示应跳过识别。

    注意：只看文书**类型名**部分，文件名里的案件描述可能含任意字词，
    因此用整串匹配而不是按「（）」切分后再匹配——切分规则一变就会误判。
    """
    if not filename:
        return False
    name = str(filename).strip()
    return any(pattern.search(name) for pattern in _TEMPLATE_PATTERNS)


def filter_recognizable_documents(filenames: list[str]) -> tuple[list[str], list[str]]:
    """把文书分成「送识别」与「跳过（模板）」两组，便于调用方记录跳过原因。"""
    keep: list[str] = []
    skipped: list[str] = []
    for name in filenames:
        (skipped if is_template_document(name) else keep).append(name)
    return keep, skipped
