"""页范围解析：把用户给的页规格解成 1-based 页码列表。"""

from __future__ import annotations

import re

#: 单次调用最多渲染页数（防一次拖 300 页扫描件打爆时间与上下文）。
DEFAULT_MAX_PAGES = 20

_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


def parse_pages(
    spec: str | int | list[int] | tuple[int, ...] | None,
    total_pages: int,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> tuple[list[int], int]:
    """把用户给的页范围解成 1-based 页码列表，返回 ``(pages, truncated_count)``。

    支持形态：``"1-3"``（区间）/ ``"7"``（单页）/ ``"all"`` / ``"1,3,5"`` /
    ``[1, 5]`` / ``None``（默认前 ``max_pages`` 页）。对外一律 1-based——
    对律师说「第 0 页」没有意义。

    Raises:
        ValueError: 页码超出 ``[1, total_pages]``（调用方转 ``page_out_of_range``）。
            这里用异常而不是返回值，是因为「越界」不是可降级的结果：整次请求
            没有意义，必须让调用方拿到明确的失败信号，不能悄悄夹逼到边界页。
    """
    limit = max(1, int(max_pages))
    if spec is None or (isinstance(spec, str) and not spec.strip()) or spec == "all":
        pages = list(range(1, total_pages + 1))
    else:
        pages = _expand_spec(spec, total_pages)
    unique = sorted(set(pages))
    if not unique:
        raise ValueError(f"没有可用的页码：{spec!r}")
    return unique[:limit], max(0, len(unique) - limit)


def _expand_spec(spec: str | int | list[int] | tuple[int, ...], total_pages: int) -> list[int]:
    if isinstance(spec, int):
        _check_page(spec, total_pages)
        return [spec]
    if isinstance(spec, list | tuple):
        out: list[int] = []
        for item in spec:
            _check_page(int(item), total_pages)
            out.append(int(item))
        return out

    out = []
    for part in str(spec).replace("，", ",").split(","):
        token = part.strip()
        if not token:
            continue
        matched = _RANGE_RE.match(token)
        if matched:
            start, end = int(matched.group(1)), int(matched.group(2))
            if start > end:
                raise ValueError(f"页区间起点大于终点：{token!r}")
            _check_page(start, total_pages)
            _check_page(end, total_pages)
            out.extend(range(start, end + 1))
            continue
        if not token.isdigit():
            raise ValueError(f"无法解析的页范围：{token!r}（应形如 '1-3' / '7' / 'all'）")
        _check_page(int(token), total_pages)
        out.append(int(token))
    return out


def _check_page(page_no: int, total_pages: int) -> None:
    if page_no < 1 or page_no > max(1, total_pages):
        raise ValueError(f"页码 {page_no} 超出范围 [1, {total_pages}]")
