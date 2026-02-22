"""Module for range."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _parse_suffix_range(end_s: str, file_size: int) -> tuple[int, int] | None:
    """处理后缀范围请求,如 bytes=-500"""
    try:
        suffix = int(end_s)
    except (ValueError, TypeError):
        return None
    if suffix <= 0:
        return None
    start = max(0, file_size - suffix)
    return (start, file_size - 1)


def _parse_explicit_range(start_s: str, end_s: str, file_size: int) -> tuple[int, int] | None:
    """处理显式范围请求,如 bytes=0-499"""
    try:
        start = int(start_s)
    except (ValueError, TypeError):
        return None
    if start < 0:
        return None

    if end_s == "":
        end = file_size - 1
    else:
        try:
            end = int(end_s)
        except (ValueError, TypeError):
            return None

    if end < start:
        return None
    end = min(end, file_size - 1)
    start = min(start, file_size - 1)
    return (start, end)


def parse_range_header(range_header: str, file_size: int) -> tuple[int, int] | None:
    if not range_header or not range_header.startswith("bytes="):
        return None
    value = range_header[len("bytes=") :].strip()
    if "," in value:
        value = value.split(",", 1)[0].strip()
    if "-" not in value:
        return None
    start_s, end_s = value.split("-", 1)
    start_s = start_s.strip()
    end_s = end_s.strip()

    if start_s == "":
        return _parse_suffix_range(end_s, file_size)
    return _parse_explicit_range(start_s, end_s, file_size)
