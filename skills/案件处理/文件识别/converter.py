"""
文件识别 Skill - 核心转换逻辑

调用后端文档解析 API,将各种格式文件统一转为 Markdown。
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils import DEFAULT_POLL_INTERVAL, DEFAULT_POLL_TIMEOUT, APIClient, DocumentParsingClient, build_api_client
from .detector import detect_file_format, is_format_supported, select_backend
from .formats import DEFAULT_BACKEND
from .utils import generate_md_output_path

logger = logging.getLogger(__name__)

__all__ = ['recognize_file', 'recognize_files']


def recognize_file(
    file_path: str | Path,
    backend: str = DEFAULT_BACKEND,
    output_dir: str | Path | None = None,
    api_client: APIClient | None = None,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    poll_timeout: float = DEFAULT_POLL_TIMEOUT,
) -> dict:
    """识别单个文件,转为 Markdown

    Args:
        file_path: 输入文件路径
        backend: 解析后端(auto/mineru/textin/local)
        output_dir: 输出目录(可选,默认与输入同目录)
        api_client: 已认证的 APIClient(可选,未提供则从环境变量构建)
        poll_interval: 异步任务轮询间隔(秒)
        poll_timeout: 异步任务最大等待时间(秒)

    Returns:
        结果 dict,字段:
        - success: bool
        - input: str(输入路径)
        - output: str | None(输出 md 路径)
        - backend: str | None(实际使用的后端)
        - parse_method: str | None
        - metadata: dict | None
        - markdown_length: int | None
        - error: str | None
    """
    file_path = Path(file_path)
    base_result: dict = {
        'success': False,
        'input': str(file_path),
        'output': None,
        'backend': None,
        'parse_method': None,
        'metadata': None,
        'markdown_length': None,
        'error': None,
    }

    # 校验文件
    if not file_path.exists():
        base_result['error'] = '文件不存在'
        return base_result
    if not file_path.is_file():
        base_result['error'] = '不是文件'
        return base_result
    if not is_format_supported(file_path):
        fmt = detect_file_format(file_path)
        base_result['error'] = f'不支持的格式: .{fmt}'
        return base_result

    # 选择后端
    try:
        actual_backend = select_backend(file_path, backend)
    except ValueError as e:
        base_result['error'] = str(e)
        return base_result
    base_result['backend'] = actual_backend

    # 构建 API 客户端
    if api_client is None:
        try:
            api_client = build_api_client()
        except ValueError as e:
            base_result['error'] = str(e)
            return base_result

    parsing_client = DocumentParsingClient(
        api_client, poll_interval=poll_interval, poll_timeout=poll_timeout
    )

    # 调用解析
    logger.info('解析文件: %s (backend=%s)', file_path.name, actual_backend)
    try:
        result = parsing_client.parse(
            file_path, backend=actual_backend, return_markdown=True
        )
    except (RuntimeError, ConnectionError, PermissionError) as e:
        base_result['error'] = f'API 调用失败: {e}'
        return base_result

    if not result['success']:
        base_result['error'] = result.get('error', '解析失败')
        return base_result

    # 保存 Markdown
    md = result.get('markdown') or result.get('text') or ''
    if not md:
        base_result['error'] = '解析结果为空(markdown 和 text 均无内容)'
        return base_result

    output_path = generate_md_output_path(file_path, output_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding='utf-8')

    base_result.update({
        'success': True,
        'output': str(output_path),
        'parse_method': result.get('parse_method'),
        'metadata': result.get('metadata'),
        'markdown_length': len(md),
    })
    logger.info('✓ %s → %s (%d 字符)', file_path.name, output_path, len(md))
    return base_result


def recognize_files(
    file_paths: list[str | Path],
    backend: str = DEFAULT_BACKEND,
    output_dir: str | Path | None = None,
    api_client: APIClient | None = None,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    poll_timeout: float = DEFAULT_POLL_TIMEOUT,
) -> list[dict]:
    """批量识别文件

    复用同一个 api_client,避免重复登录。

    Args:
        file_paths: 文件路径列表
        其他参数同 recognize_file

    Returns:
        结果 dict 列表(顺序与输入一致)
    """
    # 统一构建一次 api_client
    if api_client is None:
        try:
            api_client = build_api_client()
        except ValueError as e:
            return [
                {
                    'success': False,
                    'input': str(p),
                    'output': None,
                    'backend': None,
                    'parse_method': None,
                    'metadata': None,
                    'markdown_length': None,
                    'error': str(e),
                }
                for p in file_paths
            ]

    results: list[dict] = []
    for p in file_paths:
        r = recognize_file(
            p,
            backend=backend,
            output_dir=output_dir,
            api_client=api_client,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )
        results.append(r)
        if r['success']:
            logger.info('✓ %s → %s', r['input'], r['output'])
        else:
            logger.error('✗ %s: %s', r['input'], r.get('error'))
    return results
