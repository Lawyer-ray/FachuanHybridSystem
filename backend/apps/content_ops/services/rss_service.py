"""RSS Feed 生成服务 — 生成播客 RSS 2.0 XML。"""

from __future__ import annotations

import logging
from xml.etree.ElementTree import Element, SubElement, tostring

from apps.content_ops.models import PodcastEpisode, ReviewStatus

logger = logging.getLogger(__name__)


class RSSService:
    """生成播客 RSS 2.0 Feed。"""

    def generate_feed(self, *, request_host: str) -> str:
        """生成 RSS XML 字符串。"""
        episodes = (
            PodcastEpisode.objects.filter(
                review_status=ReviewStatus.APPROVED,
                article__review_status=ReviewStatus.APPROVED,
            )
            .select_related("article", "task")
            .order_by("-created_at")[:100]
        )

        rss = Element("rss", version="2.0")
        channel = SubElement(rss, "channel")

        SubElement(channel, "title").text = "法穿AI · 法律故事播客"
        SubElement(channel, "link").text = request_host
        SubElement(channel, "description").text = "用街坊邻居的口吻，讲述真实的法律故事"
        SubElement(channel, "language").text = "zh-cn"

        for ep in episodes:
            item = SubElement(channel, "item")
            SubElement(item, "title").text = ep.article.title
            SubElement(item, "description").text = ep.article.source_summary or ep.article.title

            audio_url = f"{request_host}{ep.audio_file.url}" if ep.audio_file else ""
            enclosure = SubElement(item, "enclosure")
            enclosure.set("url", audio_url)
            enclosure.set("type", "audio/mpeg")
            if ep.file_size_bytes:
                enclosure.set("length", str(ep.file_size_bytes))

            SubElement(item, "guid").text = f"episode-{ep.pk}"
            SubElement(item, "pubDate").text = ep.created_at.strftime("%a, %d %b %Y %H:%M:%S +0800")

        return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(rss, encoding="unicode")
