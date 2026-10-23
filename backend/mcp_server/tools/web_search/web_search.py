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

# 简单限流：每分钟最多 20 次请求（防止被搜狗封 IP）
#
# 这是**进程级**配额：共享 MCP（streamable-http :8011）下所有律师的 agent
# 共用一个计数器。因此超限时不能阻塞等待：
# - 旧实现 `time.sleep(wait)` 最长卡 59 秒（实测），该次工具调用整体挂起，
#   模型只能干等——而它本来可以用“搜不了，我换种方式回答”来收场；
# - 一个人的高频搜索会把全所拖慢。
# 现改为**快速失败**：超限立即返回明确原因，由工具层转成可读提示。
_last_requests: list[float] = []
_RATE_LIMIT = 20
_RATE_WINDOW = 60.0


class RateLimitedError(RuntimeError):
    """搜索配额已用完（不是网络错误，不需要重试）。"""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"搜索请求过于频繁，请 {retry_after} 秒后再试")


def _rate_limit() -> None:
    """登记一次请求；配额不足时**立即抛错**，绝不阻塞。

    Raises:
        RateLimitedError: 当前 60 秒窗口内的请求数已达上限。
    """
    now = time.monotonic()
    _last_requests[:] = [t for t in _last_requests if now - t < _RATE_WINDOW]
    if len(_last_requests) >= _RATE_LIMIT:
        retry_after = max(1, int(_RATE_WINDOW - (now - _last_requests[0])) + 1)
        raise RateLimitedError(retry_after)
    _last_requests.append(now)


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
    """同步执行搜索（在线程池中运行）。

    限流/网络错误一律转成**给模型看的自然语言**，不抛异常：
    模型读到提示就能换种方式回答（告知用户稍后再试），而不是把整轮对话
    拖到报错。
    """
    try:
        _rate_limit()
    except RateLimitedError as exc:
        return f"{exc}。本次无法联网搜索，请先用已有知识回答，或告知用户稍后再试。"

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
    """联网搜索互联网获取最新信息。适用于查询实时新闻、最新法规、行业动态。

    Args:
        query: 搜索关键词（建议用中文或英文关键词，简洁明了）。
        max_results: 最大返回结果数量，默认 5 条，上限 10。
        region: 保留参数，当前固定使用中文搜狗，传值不影响行为。

    Returns:
        自然语言搜索结果（标题 + 链接 + 摘要）。

    Notes:
        - 本工具受**进程级**配额限制（每分钟 20 次，全所共享）。超限时直接
          返回提示而**不阻塞等待**——模型应用已有知识回答或建议稍后再试。
        - 结果里的链接是搜索引擎跳转形式，不是原文地址。
        - **当前日期/时间**请用 ``get_server_time``，不要从搜索结果摘要里抄——
          摘要常含多个互相矛盾的时间戳。
    """
    if not query.strip():
        return "搜索关键词不能为空"

    max_results = min(max(max_results, 1), 10)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _do_search, query, max_results, region)
