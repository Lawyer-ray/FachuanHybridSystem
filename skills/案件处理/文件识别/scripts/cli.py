"""
文件识别 Skill - 命令行入口

用法:
    # 单文件
    python -m skills.案件处理.文件识别.scripts /path/to/document.pdf

    # 目录(递归扫描)
    python -m skills.案件处理.文件识别.scripts /path/to/case_folder --recursive

    # 指定输出目录和后端
    python -m skills.案件处理.文件识别.scripts /path/to/file.pdf --output-dir /output --backend textin

认证(按优先级):
    1. --token 参数 或 FACHUAN_API_TOKEN 环境变量
    2. --username/--password 参数 或 FACHUAN_USERNAME/FACHUAN_PASSWORD 环境变量
    3. --base-url 参数 或 FACHUAN_BASE_URL 环境变量(默认 http://127.0.0.1:8002)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ..._shared import build_api_client
from .converter import recognize_file, recognize_files
from .detector import is_format_supported, scan_directory
from .formats import ALL_SUPPORTED_FORMATS, DEFAULT_BACKEND
from .utils import format_result_summary

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog='python -m skills.案件处理.文件识别.scripts',
        description='文件识别:将各种格式(PDF/DOC/DOCX/图片等)统一转为 Markdown',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '支持的格式:\n  '
            + ', '.join(sorted(ALL_SUPPORTED_FORMATS))
            + '\n\n认证(按优先级):\n'
            '  1. --token 或 FACHUAN_API_TOKEN\n'
            '  2. --username/--password 或 FACHUAN_USERNAME/FACHUAN_PASSWORD\n'
            '  3. --base-url 或 FACHUAN_BASE_URL (默认 http://127.0.0.1:8002)'
        ),
    )
    parser.add_argument(
        'input',
        help='输入文件或目录路径',
    )
    parser.add_argument(
        '-b', '--backend',
        choices=['auto', 'mineru', 'textin', 'local'],
        default=DEFAULT_BACKEND,
        help=f'解析后端(默认 {DEFAULT_BACKEND})',
    )
    parser.add_argument(
        '-o', '--output-dir',
        help='输出目录(默认与输入文件同目录)',
    )
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='输入为目录时,递归扫描子目录',
    )
    parser.add_argument(
        '--base-url',
        help='后端服务地址(默认读 FACHUAN_BASE_URL 或 http://127.0.0.1:8002)',
    )
    parser.add_argument(
        '--token',
        help='JWT Token(优先于用户名密码)',
    )
    parser.add_argument(
        '--username',
        help='登录用户名',
    )
    parser.add_argument(
        '--password',
        help='登录密码',
    )
    parser.add_argument(
        '--poll-interval',
        type=float,
        default=2.0,
        help='异步任务轮询间隔(秒,默认 2.0)',
    )
    parser.add_argument(
        '--poll-timeout',
        type=float,
        default=600.0,
        help='异步任务最大等待时间(秒,默认 600)',
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
        退出码: 0=全部成功, 1=部分失败, 2=全部失败/参数错误
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(message)s',
    )

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error('路径不存在: %s', input_path)
        return 2

    # 收集待识别文件
    if input_path.is_file():
        if not is_format_supported(input_path):
            logger.error('不支持的文件格式: %s', input_path.suffix)
            return 2
        file_list = [input_path]
    else:
        file_list = scan_directory(input_path, recursive=args.recursive)
        if not file_list:
            logger.error('目录中没有支持的文件: %s', input_path)
            logger.error('支持格式: %s', ', '.join(sorted(ALL_SUPPORTED_FORMATS)))
            return 2
        logger.info('扫描到 %d 个文件', len(file_list))

    # 构建 API 客户端
    try:
        api_client = build_api_client(
            base_url=args.base_url,
            token=args.token,
            username=args.username,
            password=args.password,
        )
    except ValueError as e:
        logger.error(str(e))
        return 2

    # 执行识别
    if len(file_list) == 1:
        result = recognize_file(
            file_list[0],
            backend=args.backend,
            output_dir=args.output_dir,
            api_client=api_client,
            poll_interval=args.poll_interval,
            poll_timeout=args.poll_timeout,
        )
        results = [result]
    else:
        results = recognize_files(
            file_list,
            backend=args.backend,
            output_dir=args.output_dir,
            api_client=api_client,
            poll_interval=args.poll_interval,
            poll_timeout=args.poll_timeout,
        )

    # 汇总结果
    logger.info(format_result_summary(results))

    success_count = sum(1 for r in results if r['success'])
    if success_count == len(results):
        return 0
    if success_count == 0:
        return 2
    return 1


if __name__ == '__main__':
    sys.exit(main())
