"""
按标题拆分 Skill - 拆分执行逻辑

职责:
- apply_split_map:按 AI 给的拆分方案,把 md 切成多个文件
- split_document:规则模式(兜底,按 ## 标题切分)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .detector import detect_heading_candidates
from .formats import MIN_CHUNK_CHARS
from .utils import generate_output_path, sanitize_filename, validate_md_input

logger = logging.getLogger(__name__)

__all__ = ['apply_split_map', 'split_document']


def apply_split_map(
    input_path: str | Path,
    split_map: str | list[dict],
    output_dir: str | Path | None = None,
) -> dict:
    """根据 AI 提供的拆分方案,把 markdown 切成多个文件

    Args:
        input_path: 输入 .md 文件路径
        split_map: AI 生成的拆分方案,可以是 JSON 字符串或已解析的列表
                   格式: [{"name": "民事起诉状", "start_line": 557, "end_line": 677,
                            "type": "起诉状", "is_noise": false}, ...]
        output_dir: 输出目录(可选,默认为输入同目录下的 {stem}_split/)

    Returns:
        dict: 拆分结果
        - success: bool
        - input_path: str
        - output_dir: str
        - total_chunks: int
        - chunks: list[dict](每个含 index/name/type/output/line_count/char_count)
        - error: str | None
    """
    # 验证输入
    try:
        path = validate_md_input(input_path)
    except (FileNotFoundError, ValueError) as e:
        return {'success': False, 'error': str(e)}

    # 解析 split_map
    if isinstance(split_map, str):
        try:
            mapping_data = json.loads(split_map)
        except json.JSONDecodeError as e:
            return {'success': False, 'error': f'拆分方案 JSON 解析失败: {e}'}
    else:
        mapping_data = split_map

    if not isinstance(mapping_data, list) or not mapping_data:
        return {'success': False, 'error': '拆分方案必须是非空 JSON 数组'}

    # 读取 md 全文
    md_text = path.read_text(encoding='utf-8')
    lines = md_text.split('\n')
    total_lines = len(lines)

    # 校验并排序拆分方案(按 start_line)
    try:
        mapping_data.sort(key=lambda x: x['start_line'])
    except (KeyError, TypeError) as e:
        return {'success': False, 'error': f'拆分方案缺少 start_line 字段: {e}'}

    # 确定输出目录
    if output_dir is None:
        output_dir = path.parent / f'{path.stem}_split'
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 执行拆分
    chunks: list[dict] = []
    for i, item in enumerate(mapping_data):
        name = item.get('name') or f'片段{i + 1}'
        start = int(item.get('start_line', 0))
        end = int(item.get('end_line', total_lines - 1))
        doc_type = item.get('type', '')
        is_noise = item.get('is_noise', False)

        # 边界保护
        start = max(0, min(start, total_lines - 1))
        end = max(start, min(end, total_lines - 1))

        # 提取片段内容
        chunk_lines = lines[start:end + 1]
        chunk_text = '\n'.join(chunk_lines)

        # 跳过过短的噪音片段
        if is_noise and len(chunk_text.strip()) < MIN_CHUNK_CHARS:
            logger.info('跳过过短的噪音片段: %s (%d 字符)', name, len(chunk_text))
            continue

        # 生成输出路径
        out_path = generate_output_path(name, output_dir, len(chunks), len(mapping_data))

        # 如果是噪音片段,文件名加前缀便于识别
        if is_noise:
            out_path = out_path.with_name(f'00_noise_{out_path.name}')

        out_path.write_text(chunk_text, encoding='utf-8')

        chunks.append({
            'index': len(chunks),
            'name': name,
            'type': doc_type,
            'is_noise': is_noise,
            'start_line': start,
            'end_line': end,
            'output': str(out_path),
            'line_count': len(chunk_lines),
            'char_count': len(chunk_text),
        })
        logger.info('✓ %s → %s (%d 行, %d 字符)', name, out_path.name, len(chunk_lines), len(chunk_text))

    return {
        'success': True,
        'input_path': str(path),
        'output_dir': str(output_dir),
        'total_chunks': len(chunks),
        'chunks': chunks,
        'error': None,
    }


def split_document(
    input_path: str | Path,
    output_dir: str | Path | None = None,
    level: int = 2,
) -> dict:
    """规则模式:按指定层级的 markdown 标题切分(兜底,效果有限)

    ⚠️ 此模式仅作为兜底,对于真实案件材料(标题层级混乱)效果不好。
    推荐使用 AI 辅助模式(--analyze + --apply-map)。

    Args:
        input_path: 输入 .md 文件路径
        output_dir: 输出目录(可选)
        level: 按哪一级标题切分(默认 2,即 ##)

    Returns:
        dict: 同 apply_split_map
    """
    try:
        path = validate_md_input(input_path)
    except (FileNotFoundError, ValueError) as e:
        return {'success': False, 'error': str(e)}

    md_text = path.read_text(encoding='utf-8')
    lines = md_text.split('\n')
    candidates = detect_heading_candidates(md_text)

    # 筛选指定层级的候选标题
    target_candidates = [c for c in candidates if c['level'] == level]

    if not target_candidates:
        return {
            'success': False,
            'error': f'未找到层级 {level} 的标题行,无法切分。请使用 --analyze 模式让 AI 判断。',
        }

    # 构建拆分方案
    prefix = '#' * level + ' '
    split_map_data: list[dict] = []

    # 第一个片段:从文件开头到第一个目标标题前
    first = target_candidates[0]
    if first['line_no'] > 0:
        split_map_data.append({
            'name': '文件开头',
            'start_line': 0,
            'end_line': first['line_no'] - 1,
            'type': '前言',
            'is_noise': first['line_no'] < 5,
        })

    # 每个目标标题作为一个片段的起点
    for i, c in enumerate(target_candidates):
        start = c['line_no']
        end = (target_candidates[i + 1]['line_no'] - 1
               if i + 1 < len(target_candidates)
               else len(lines) - 1)
        split_map_data.append({
            'name': c['text'],
            'start_line': start,
            'end_line': end,
            'type': '',
            'is_noise': c.get('is_noise', False),
        })

    logger.info('规则模式:按 %s 标题切分为 %d 个片段', prefix, len(split_map_data))
    return apply_split_map(path, split_map_data, output_dir)
