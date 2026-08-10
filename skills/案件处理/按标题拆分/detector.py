"""
按标题拆分 Skill - 候选标题检测

职责:
- 扫描 markdown,识别所有候选标题行(markdown 标题 + 可能的文书名)
- 为每个候选标题提取上下文,供 AI 判断
- 输出结构化 JSON

注意:本模块只做"检测",不做"判断"。
哪些候选标题是真正的拆分点,由 AI(analyze 模式)或规则(自动模式)决定。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .formats import MARKDOWN_HEADING_PREFIXES, NOISE_KEYWORDS
from .utils import validate_md_input

logger = logging.getLogger(__name__)

__all__ = ['detect_heading_candidates', 'analyze_structure']

# 上下文预览长度(每个候选标题前后各取多少字符)
CONTEXT_CHARS = 200


def detect_heading_candidates(md_text: str) -> list[dict]:
    """检测 markdown 中的所有候选标题行

    候选标题包括:
    1. markdown 标题行(以 # 开头)
    2. 全行加粗的短行(可能是文书名,**xxx**)

    Args:
        md_text: markdown 全文

    Returns:
        候选标题列表,每项:
        - index: 候选序号(0-based)
        - line_no: 行号(0-based)
        - text: 标题文本(已去除 # 和 ** 标记)
        - raw: 原始行内容
        - level: 标题层级(1-6 对应 #-######,0 表示加粗行)
        - is_noise: 是否疑似噪音(封套/说明等)
        - context_before: 前 200 字符
        - context_after: 后 200 字符
    """
    lines = md_text.split('\n')
    candidates: list[dict] = []

    # 构建字符级偏移用于提取上下文
    char_offsets: list[int] = []
    pos = 0
    for line in lines:
        char_offsets.append(pos)
        pos += len(line) + 1  # +1 for \n

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        text = ''
        level = -1

        # 1. markdown 标题行
        for lvl in range(6, 0, -1):
            prefix = '#' * lvl + ' '
            if stripped.startswith(prefix):
                text = stripped[len(prefix):].strip()
                level = lvl
                break

        # 2. 全行加粗的短行(可能是文书名)
        # 匹配 **xxx** 或 __xxx__,且行长度较短(< 40 字符)
        if level == -1:
            if stripped.startswith('**') and stripped.endswith('**') and len(stripped) < 80:
                inner = stripped[2:-2].strip()
                if inner and len(inner) < 40 and not inner.startswith('<'):
                    text = inner
                    level = 0

        if level == -1 or not text:
            continue

        # 判断是否疑似噪音
        is_noise = any(kw in text for kw in NOISE_KEYWORDS)

        # 提取上下文
        start = char_offsets[i]
        end = start + len(lines[i])
        ctx_before = md_text[max(0, start - CONTEXT_CHARS):start].strip()
        ctx_after = md_text[end:end + CONTEXT_CHARS].strip()

        candidates.append({
            'index': len(candidates),
            'line_no': i,
            'text': text,
            'raw': stripped,
            'level': level,
            'is_noise': is_noise,
            'context_before': ctx_before[-CONTEXT_CHARS:] if ctx_before else '',
            'context_after': ctx_after[:CONTEXT_CHARS] if ctx_after else '',
        })

    return candidates


def analyze_structure(input_path: str | Path) -> str:
    """分析 markdown 结构,输出 JSON 供 AI 判断拆分点

    AI 拿到 JSON 后,根据语义理解:
    - 哪些候选标题是"独立法律文书的开始"(拆分点)
    - 哪些是噪音(封套/说明/正文片段)
    - 每个拆分片段的名称和文书类型

    然后生成 split_map.json:
    [
        {"name": "EMS封套", "start_line": 8, "end_line": 63, "type": "EMS封套", "is_noise": true},
        {"name": "送达回证", "start_line": 64, "end_line": 140, "type": "送达回证"},
        ...
    ]

    Args:
        input_path: markdown 文件路径

    Returns:
        JSON 字符串,结构:
        {
            "total_lines": 6500,
            "total_chars": 148712,
            "source_file": "xxx.md",
            "candidates": [
                {
                    "index": 0,
                    "line_no": 8,
                    "text": "邮政特快专递封套EMS业务使用说明",
                    "level": 1,
                    "is_noise": true,
                    "context_before": "...",
                    "context_after": "..."
                },
                ...
            ],
            "hint": "请根据候选标题的文本和上下文,判断哪些是独立法律文书的开始..."
        }
    """
    path = validate_md_input(input_path)
    md_text = path.read_text(encoding='utf-8')
    lines = md_text.split('\n')
    candidates = detect_heading_candidates(md_text)

    result = {
        'source_file': str(path),
        'total_lines': len(lines),
        'total_chars': len(md_text),
        'candidate_count': len(candidates),
        'candidates': candidates,
        'hint': (
            '请根据候选标题的 text、level、context_before、context_after 判断:\n'
            '1. 哪些候选标题是"一份独立法律文书的开始"(拆分点)\n'
            '2. 哪些是噪音(EMS封套/填写说明/正文片段,标记 is_noise=true)\n'
            '3. 为每个拆分片段起一个简洁的文件名(name)和文书类型(type)\n'
            '4. start_line 和 end_line 是行号(0-based),end_line 是该片段最后一行\n'
            '5. 第一个片段的 start_line 通常为 0(包含文件开头的非标题内容)\n'
            '6. 相邻片段的 end_line + 1 = 下一个片段的 start_line\n'
            '输出 JSON 数组:\n'
            '[{"name": "民事起诉状", "start_line": 557, "end_line": 677, "type": "起诉状"}, ...]'
        ),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)
