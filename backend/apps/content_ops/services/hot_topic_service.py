"""热点话题采集服务 — 从国内自媒体平台获取热搜/热榜数据。"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from django.core.cache import cache

from apps.core.http.httpx_clients import get_sync_http_client

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "content_ops:hot_topics"
CACHE_TTL = 1800  # 30 minutes

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# 法律科技关键词（中英文）
LEGAL_TECH_KEYWORDS = [
    # 中文
    "法律",
    "律师",
    "法院",
    "法官",
    "司法",
    "诉讼",
    "仲裁",
    "调解",
    "合同",
    "知识产权",
    "专利",
    "商标",
    "著作权",
    "合规",
    "风控",
    "法务",
    "法治",
    "立法",
    "法规",
    "条例",
    "判决",
    "裁定",
    "AI",
    "人工智能",
    "大模型",
    "GPT",
    "智能",
    "数字化",
    "区块链",
    # 英文
    "legal",
    "law",
    "lawyer",
    "attorney",
    "court",
    "judge",
    "litigation",
    "arbitration",
    "compliance",
    "contract",
    "IP",
    "patent",
    "trademark",
    "regulation",
    "statute",
    "verdict",
    "ruling",
    "AI",
    "artificial intelligence",
    "LLM",
    "GPT",
    "blockchain",
    "smart contract",
]

@dataclass
class HotTopicItem:
    """单条热点话题。"""

    rank: int
    title: str
    heat: int | None = None
    url: str = ""
    source: str = ""

def _fetch_toutiao(limit: int = 50) -> list[HotTopicItem]:
    """从今日头条获取热搜榜。"""
    url = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
    client = get_sync_http_client()
    resp = client.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    items: list[HotTopicItem] = []
    for i, entry in enumerate(data.get("data", [])[:limit]):
        title = entry.get("Title") or entry.get("QueryWord", "")
        if not title:
            continue
        heat_raw = entry.get("HotValue")
        heat = int(heat_raw) if heat_raw and str(heat_raw).isdigit() else None
        items.append(
            HotTopicItem(
                rank=i + 1,
                title=title,
                heat=heat,
                url=entry.get("Url", ""),
                source="toutiao",
            )
        )
    return items

def _fetch_baidu(limit: int = 50) -> list[HotTopicItem]:
    """从百度获取热搜榜（解析 HTML 中嵌入的 JSON）。"""
    url = "https://top.baidu.com/board?tab=realtime"
    client = get_sync_http_client()
    resp = client.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    html = resp.text

    # 百度热搜页面将数据嵌入 HTML 中的 JSON 数组
    # 提取 "content":[...] 中的数组
    queries: list[str] = re.findall(r'"query":"((?:[^"\\]|\\.)*)"', html)
    scores: list[str] = re.findall(r'"hotScore":"(\d+)"', html)
    raw_urls: list[str] = re.findall(r'"rawUrl":"((?:[^"\\]|\\.)*)"', html)

    items: list[HotTopicItem] = []
    for i, (query, score) in enumerate(zip(queries, scores)):
        if i >= limit:
            break
        heat = int(score) if score.isdigit() else None
        item_url = raw_urls[i] if i < len(raw_urls) else ""
        items.append(
            HotTopicItem(
                rank=i + 1,
                title=query,
                heat=heat,
                url=item_url,
                source="baidu",
            )
        )
    return items

def _fetch_douyin(limit: int = 50) -> list[HotTopicItem]:
    """从抖音获取热搜榜。"""
    url = "https://www.douyin.com/aweme/v1/web/hot/search/list/"
    client = get_sync_http_client()
    headers = {**_HEADERS, "Referer": "https://www.douyin.com/hot"}
    resp = client.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    items: list[HotTopicItem] = []
    for i, entry in enumerate(data.get("data", {}).get("word_list", [])[:limit]):
        title = entry.get("word", "")
        if not title:
            continue
        heat_raw = entry.get("hot_value")
        heat = int(heat_raw) if heat_raw and str(heat_raw).isdigit() else None
        items.append(
            HotTopicItem(
                rank=i + 1,
                title=title,
                heat=heat,
                url="",
                source="douyin",
            )
        )
    return items

def _fetch_36kr(limit: int = 50) -> list[HotTopicItem]:
    """从36氪获取热榜。"""
    url = "https://gateway.36kr.com/api/mis/nav/home/nav/rank/hot"
    client = get_sync_http_client()
    resp = client.post(
        url,
        headers={**_HEADERS, "Content-Type": "application/json"},
        json={"partner_id": "wap", "param": {"siteId": 1, "platformId": 2}},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    items: list[HotTopicItem] = []
    for i, entry in enumerate(data.get("data", {}).get("hotRankList", [])[:limit]):
        title = entry.get("templateMaterial", {}).get("widgetTitle", "")
        if not title:
            continue
        item_id = entry.get("itemId", 0)
        heat = entry.get("templateMaterial", {}).get("statRead")
        items.append(
            HotTopicItem(
                rank=i + 1,
                title=title,
                heat=int(heat) if heat and str(heat).isdigit() else None,
                url=f"https://36kr.com/p/{item_id}" if item_id else "",
                source="36kr",
            )
        )
    return items

def _fetch_thepaper(limit: int = 50) -> list[HotTopicItem]:
    """从澎湃新闻获取热榜。"""
    url = "https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar"
    client = get_sync_http_client()
    resp = client.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    items: list[HotTopicItem] = []
    for i, entry in enumerate(data.get("data", {}).get("hotNews", [])[:limit]):
        title = entry.get("name", "")
        if not title:
            continue
        cont_id = entry.get("contId", "")
        items.append(
            HotTopicItem(
                rank=i + 1,
                title=title,
                heat=None,
                url=f"https://www.thepaper.cn/newsDetail_forward_{cont_id}" if cont_id else "",
                source="thepaper",
            )
        )
    return items

def _is_legal_tech_related(title: str) -> bool:
    """判断标题是否与法律科技相关。"""
    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in LEGAL_TECH_KEYWORDS)

def _fetch_rss_feed(name: str, url: str, limit: int = 20) -> list[HotTopicItem]:
    """从 RSS 源获取法律科技新闻。"""
    client = get_sync_http_client()
    resp = client.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()

    items: list[HotTopicItem] = []
    try:
        root = ET.fromstring(resp.text)
        for i, entry in enumerate(root.findall(".//item")[:limit]):
            title_el = entry.find("title")
            link_el = entry.find("link")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            if title:
                items.append(
                    HotTopicItem(
                        rank=i + 1,
                        title=title,
                        heat=None,
                        url=link,
                        source=name,
                    )
                )
    except ET.ParseError:
        logger.warning("Failed to parse RSS feed from %s", name)
    return items

def _scrape_with_playwright(name: str, url: str, limit: int = 10) -> list[HotTopicItem]:
    """使用 Playwright 爬取网站标题。"""
    from apps.core.services.browser import create_browser

    items: list[HotTopicItem] = []
    try:
        with create_browser() as (page, context):
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            content = page.content()

            # 提取标题（多种模式）
            titles = re.findall(r"<h[1-3][^>]*>([^<]+)</h[1-3]>", content)
            if not titles:
                titles = re.findall(r'<a[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</a>', content)
            if not titles:
                titles = re.findall(r"<h2[^>]*>([^<]+)</h2>", content)

            for i, title in enumerate(titles[:limit]):
                title = title.strip()
                if title and len(title) > 10:  # 过滤太短的标题
                    items.append(
                        HotTopicItem(
                            rank=i + 1,
                            title=title,
                            heat=None,
                            url=url,
                            source=name,
                        )
                    )
    except Exception:
        logger.exception("Failed to scrape %s with Playwright", name)
    return items

def _fetch_legaltech(limit: int = 50) -> list[HotTopicItem]:
    """获取法律科技相关新闻（并行采集，提升速度）。

    来源：
    1. 英文法律科技 RSS（LawSites、Artificial Lawyer、LawNext）
    2. 中文科技 RSS（36氪AI、InfoQ、机器之心、量子位）— 过滤法律相关
    3. 从现有中文热搜中过滤法律科技相关条目
    """
    items: list[HotTopicItem] = []
    rank = 0

    # 并行采集所有 RSS 源
    rss_tasks: list[tuple[str, str, int]] = [
        # 英文法律科技 RSS
        ("lawsites", "https://www.lawsitesblog.com/feed", 15),
        ("artificial_lawyer", "https://www.artificiallawyer.com/feed/", 15),
        ("bob_ambrogi", "https://www.lawnext.com/feed", 15),
        # 中文科技 RSS
        ("36kr_ai", "https://36kr.com/feed?tag=AI", 30),
        ("infoq", "https://www.infoq.cn/feed", 30),
        ("jiqizhixin", "https://www.jiqizhixin.com/rss", 30),
        ("qbitai", "https://www.qbitai.com/feed", 30),
    ]

    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = {
            executor.submit(_fetch_rss_feed, name, url, limit): (name, url, limit) for name, url, limit in rss_tasks
        }
        for future in as_completed(futures):
            name = futures[future][0]
            try:
                rss_items = future.result()
                # 中文 RSS 需要过滤法律相关
                if name in ("36kr_ai", "infoq", "jiqizhixin", "qbitai"):
                    rss_items = [item for item in rss_items if _is_legal_tech_related(item.title)]
                for item in rss_items:
                    rank += 1
                    item.rank = rank
                    items.append(item)
            except Exception:
                logger.exception("Failed to fetch RSS from %s", name)

    # 从现有中文热搜中过滤法律科技相关（使用缓存，速度快）
    chinese_sources = ["toutiao", "baidu", "douyin", "36kr", "thepaper"]
    for src in chinese_sources:
        try:
            # 优先使用缓存中的数据
            cache_key = f"{CACHE_KEY_PREFIX}:{src}"
            cached: list[HotTopicItem] | None = cache.get(cache_key)
            if cached is None:
                # 缓存未命中，快速采集
                cached = _SCRAPER_FN_MAP[src](limit=50)
            for topic in cached or []:
                if _is_legal_tech_related(topic.title):
                    rank += 1
                    topic.rank = rank
                    topic.source = f"{src}_legaltech"
                    items.append(topic)
        except Exception:
            logger.exception("Failed to filter legaltech from %s", src)

    return items[:limit]

# 采集器注册表（仅保留有公开 API 的来源）
_SCRAPERS: dict[str, tuple[str, type[Exception]]] = {
    "toutiao": ("头条", Exception),
    "baidu": ("百度", Exception),
    "douyin": ("抖音", Exception),
    "36kr": ("36氪", Exception),
    "thepaper": ("澎湃", Exception),
    "legaltech": ("法律科技", Exception),
}

_SCRAPER_FN_MAP: dict[str, Any] = {
    "toutiao": _fetch_toutiao,
    "baidu": _fetch_baidu,
    "douyin": _fetch_douyin,
    "36kr": _fetch_36kr,
    "thepaper": _fetch_thepaper,
    "legaltech": _fetch_legaltech,
}

class HotTopicService:
    """热点话题采集与缓存服务。"""

    def get_hot_topics(self, source: str | None = None) -> list[HotTopicItem]:
        """获取热点话题列表。优先从缓存读取。"""
        if source:
            return self._get_single_source(source)

        # 获取所有源
        return self._get_all_sources()

    def refresh(self, source: str | None = None) -> list[HotTopicItem]:
        """强制刷新（绕过缓存）。"""
        if source:
            return self._fetch_and_cache(source)

        return self._refresh_all()

    def _get_all_sources(self) -> list[HotTopicItem]:
        """获取所有源的数据。"""
        all_items: list[HotTopicItem] = []
        for src in _SCRAPERS:
            all_items.extend(self._get_single_source(src))
        return all_items

    def _refresh_all(self) -> list[HotTopicItem]:
        """强制刷新所有源。"""
        all_items: list[HotTopicItem] = []
        for src in _SCRAPERS:
            all_items.extend(self._fetch_and_cache(src))
        return all_items

    def _get_single_source(self, source: str) -> list[HotTopicItem]:
        """从缓存获取单个源的数据，缓存未命中则采集。"""
        cache_key = f"{CACHE_KEY_PREFIX}:{source}"
        cached: list[HotTopicItem] | None = cache.get(cache_key)
        if cached is not None:
            return cached
        return self._fetch_and_cache(source)

    def _fetch_and_cache(self, source: str) -> list[HotTopicItem]:
        """采集单个源的数据并写入缓存。"""
        if source not in _SCRAPER_FN_MAP:
            logger.warning("Unknown hot topic source: %s", source)
            return []

        cache_key = f"{CACHE_KEY_PREFIX}:{source}"
        fetcher = _SCRAPER_FN_MAP[source]
        label = _SCRAPERS[source][0]

        try:
            items: list[HotTopicItem] = fetcher()
            cache.set(cache_key, items, CACHE_TTL)
            logger.info("Fetched %d hot topics from %s", len(items), label)
            return items
        except Exception:
            logger.exception("Failed to fetch hot topics from %s", label)
            # 采集失败时返回缓存中的旧数据（如果有的话）
            stale: list[HotTopicItem] | None = cache.get(cache_key)
            if stale is not None:
                logger.info("Returning stale cache for %s (%d items)", label, len(stale))
            return stale or []
