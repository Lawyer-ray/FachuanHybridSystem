"""
按标题拆分 Skill - 命令行入口

三种工作模式:
1. 规则模式(默认):python -m skills.案件处理.按标题拆分.scripts input.md [output_dir] [--level 2]
2. 分析模式:python -m skills.案件处理.按标题拆分.scripts input.md --analyze
3. AI 映射模式:python -m skills.案件处理.按标题拆分.scripts input.md --apply-map map.json [output_dir]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .converter import apply_split_map, split_document
from .detector import analyze_structure
from .formats import DOCUMENT_TYPE_KEYWORDS
from .utils import format_split_summary

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog='python -m skills.案件处理.按标题拆分.scripts',
        description='按标题拆分:将包含多份文书的 markdown 拆分为多个独立 .md 文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '工作模式:\n'
            '  规则模式(默认): 按 markdown 标题层级切分,效果有限\n'
            '  分析模式: 输出候选标题 JSON,由 AI(trade/claude code)判断拆分点\n'
            '  AI 映射模式: 按 AI 生成的拆分方案执行切分\n\n'
            'AI 辅助模式流程:\n'
            '  1. python -m skills.案件处理.按标题拆分.scripts input.md --analyze > structure.json\n'
            '  2. AI 读取 structure.json,理解文档结构,生成 split_map.json\n'
            '  3. python -m skills.案件处理.按标题拆分.scripts input.md --apply-map split_map.json output_dir\n\n'
            'split_map.json 格式:\n'
            '  [{"name": "民事起诉状", "start_line": 557, "end_line": 677, "type": "起诉状"}, ...]\n\n'
            '已知文书类型(供 AI 参考):\n  '
            + ', '.join(sorted(DOCUMENT_TYPE_KEYWORDS.keys()))
        ),
    )
    parser.add_argument(
        'input',
        help='输入 markdown 文件路径',
    )
    parser.add_argument(
        'output_dir',
        nargs='?',
        help='输出目录(默认 {stem}_split/)',
    )
    parser.add_argument(
        '--analyze',
        action='store_true',
        help='分析模式:输出候选标题结构 JSON 到 stdout',
    )
    parser.add_argument(
        '--apply-map',
        metavar='MAP_FILE',
        help='AI 映射模式:读取 AI 生成的拆分方案 JSON 文件并执行拆分',
    )
    parser.add_argument(
        '--level',
        type=int,
        default=2,
        choices=[1, 2, 3, 4, 5, 6],
        help='规则模式:按哪一级标题切分(默认 2,即 ##)',
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细日志',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """命令行入口

    Returns:
        退出码: 0=成功, 1=失败
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(message)s',
    )

    # 分析模式:输出 JSON 到 stdout
    if args.analyze:
        result = analyze_structure(args.input)
        sys.stdout.write(result)
        return 0

    # AI 映射模式:读取 JSON 文件并执行拆分
    if args.apply_map:
        try:
            with open(args.apply_map, encoding='utf-8') as f:
                split_map = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error('读取拆分方案失败: %s', e)
            return 1

        result = apply_split_map(args.input, split_map, args.output_dir)
    else:
        # 规则模式(默认)
        result = split_document(args.input, args.output_dir, level=args.level)

    if result['success']:
        logger.info(format_split_summary(result['chunks']))
        return 0

    logger.error('✗ 拆分失败: %s', result.get('error', '未知错误'))
    return 1


if __name__ == '__main__':
    sys.exit(main())
