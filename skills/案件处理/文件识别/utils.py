"""
文件识别 Skill - 工具函数

提供输出路径生成、结果格式化等通用工具。
"""

from __future__ import annotations

from pathlib import Path

from .formats import MD_SUFFIX

__all__ = ['generate_md_output_path', 'format_result_summary']


def generate_md_output_path(
    input_path: str | Path, output_dir: str | Path | None = None
) -> Path:
    """生成 Markdown 输出路径

    Args:
        input_path: 输入文件路径
        output_dir: 输出目录(可选,默认与输入同目录)

    Returns:
        输出 .md 文件路径

    Examples:
        >>> generate_md_output_path('/path/to/起诉状.pdf')
        PosixPath('/path/to/起诉状.md')
        >>> generate_md_output_path('/path/to/起诉状.pdf', '/output')
        PosixPath('/output/起诉状.md')
    """
    input_path = Path(input_path)
    out_dir = Path(output_dir) if output_dir else input_path.parent
    return out_dir / f'{input_path.stem}{MD_SUFFIX}'


def format_result_summary(results: list[dict]) -> str:
    """格式化识别结果为可读字符串

    Args:
        results: recognize_files 返回的结果列表

    Returns:
        可读的汇总字符串,含完整输出路径
    """
    total = len(results)
    success = sum(1 for r in results if r.get('success'))
    failed = total - success

    # 提取输出目录(从第一个成功的结果取)
    output_dir = ''
    for r in results:
        if r.get('success') and r.get('output'):
            output_dir = str(Path(r['output']).parent)
            break

    lines = [
        '',
        '========================================',
        '  识别完成',
        '========================================',
        f'  输出目录: {output_dir}' if output_dir else '',
        f'  总计: {total} 个文件 | 成功: {success} | 失败: {failed}',
        '----------------------------------------',
    ]
    # 去掉空行(当 output_dir 为空时)
    lines = [l for l in lines if l != '' or output_dir]

    if success:
        lines.append('--- 成功 ---')
        for r in results:
            if r.get('success'):
                size = r.get('markdown_length', 0)
                lines.append(
                    f'  ✓ {r["input"]} → {r["output"]} '
                    f'({r.get("backend", "?")}, {size} 字符)'
                )

    if failed:
        lines.append('--- 失败 ---')
        for r in results:
            if not r.get('success'):
                lines.append(f'  ✗ {r["input"]}: {r.get("error", "未知错误")}')

    if output_dir:
        lines.extend([
            '----------------------------------------',
            f'  请到输出目录查看结果: {output_dir}',
            '========================================',
            '',
        ])

    return '\n'.join(lines)
