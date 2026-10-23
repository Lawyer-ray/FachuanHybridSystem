"""联网搜索与网页正文抓取 MCP tools"""

from .fetch_url import fetch_url
from .web_search import web_search

__all__ = ["web_search", "fetch_url"]
