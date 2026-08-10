"""
按标题拆分 Skill

将一个包含多份法律文书的 markdown 文件,按标题拆分为多个独立的 .md 文件。

适用场景:案件材料 PDF 经"文件识别"skill 转为单个 md 后,
其中通常包含多份文书(起诉状、传票、通知书、委托书等),
本 skill 将其拆分为每份文书一个 md,便于后续单独处理。

三种工作模式:
1. 规则模式(兜底):按 markdown 指定层级标题切分,效果有限
2. 分析模式:输出候选标题结构 JSON,由 AI 判断拆分点
3. AI 映射模式:接收 AI 生成的拆分方案,执行实际拆分
"""

from __future__ import annotations

from .converter import apply_split_map, split_document
from .detector import analyze_structure, detect_heading_candidates
from .formats import DOCUMENT_TYPE_KEYWORDS, NOISE_KEYWORDS

__version__ = '1.1.0'

__all__ = [
    'analyze_structure',
    'apply_split_map',
    'split_document',
    'detect_heading_candidates',
    'DOCUMENT_TYPE_KEYWORDS',
    'NOISE_KEYWORDS',
    '__version__',
]
