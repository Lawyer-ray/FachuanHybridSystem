"""搜狗联网搜索工具

基于搜狗搜索 HTML 接口，国内可直接访问，无需 API Key。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.sogou.com/web"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 简单限流：每分钟最多 20 次请求
_last_requests: list[float] = []
_RATE_LIMIT = 20

def _rate_limit() -> None:
    now = time.monotonic()
    _last_requests[:] = [t for t in _last_requests if now - t < 60]
    if len(_last_requests) >= _RATE_LIMIT:
        wait = 60 - (now - _last_requests[0])
        if wait > 0:
            time.sleep(wait)
    _last_requests.append(time.monotonic())

@dataclass
class _SearchResult:
    title: str
    url: str
    snippet: str

def _parse_results(html: str, max_results: int) -> list[_SearchResult]:
    """从搜狗搜索结果页面解析出搜索结果"""
    soup = BeautifulSoup(html, "html.parser")
    results: list[_SearchResult] = []

    for item in soup.select(".vrwrap, .rb")[:max_results]:
        title_el = item.select_one("h3 a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        url = title_el.get("href", "")

        # 尝试多种 snippet 选择器
        snippet = ""
        for sel in [".space-txt", ".star-wiki", ".str-text-info", ".txt-info", "p"]:
            el = item.select_one(sel)
            if el:
                snippet = el.get_text(strip=True)
                if snippet:
                    break

        if title:
            results.append(_SearchResult(title=title, url=url, snippet=snippet))

    return results

def _do_search(query: str, max_results: int, region: str) -> str:
    """同步执行搜索（在线程池中运行）"""
    _rate_limit()

    params = {
        "query": query,
    }

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(_SEARCH_URL, params=params, headers=_HEADERS)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("搜狗搜索请求失败: %s", e)
        return f"搜索请求失败: {e}"

    results = _parse_results(resp.text, max_results)

    if not results:
        return "未找到相关搜索结果，请尝试换个关键词搜索。"

    lines = [f"找到 {len(results)} 条搜索结果：\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.title}")
        if r.url:
            lines.append(f"   链接: {r.url}")
        if r.snippet:
            lines.append(f"   摘要: {r.snippet}")
        lines.append("")

    return "\n".join(lines)

async def web_search(
    query: str,
    max_results: int = 5,
    region: str = "cn-zh",
) -> str:
    """联网搜索互联网获取最新信息。适用于查询实时新闻、最新法规、行业动态、当前时间天气等。

    Args:
        query: 搜索关键词（建议用中文或英文关键词，简洁明了）
        max_results: 最大返回结果数量，默认 5 条
        region: 搜索区域（保留参数，当前固定使用中文搜狗）
    """
    if not query.strip():
        return "搜索关键词不能为空"

    max_results = min(max(max_results, 1), 10)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do_search, query, max_results, region)
