"""RSS Feed 生成服务 — 生成播客 RSS 2.0 XML。"""

from __future__ import annotations

import logging
from xml.etree.ElementTree import Element, SubElement, tostring

from django.conf import settings

from apps.content_ops.models import PodcastEpisode, ReviewStatus

logger = logging.getLogger(__name__)

class RSSService:
    """生成播客 RSS 2.0 Feed。"""

    def generate_feed(self, *, request_host: str) -> str:
        """生成 RSS XML 字符串。"""
        try:
            return self._build_feed(request_host)
        except Exception:
            logger.exception("Failed to generate RSS feed")
            return self._empty_feed(request_host)

    def _build_feed(self, request_host: str) -> str:
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

        tz_offset = self._get_timezone_offset()

        for ep in episodes:
            item = SubElement(channel, "item")
            title = ep.article.title if ep.article else ep.discussion_script.title if ep.discussion_script else ""
            SubElement(item, "title").text = title
            SubElement(item, "description").text = (ep.article.source_summary if ep.article else "") or title

            audio_url = f"{request_host}{ep.audio_file.url}" if ep.audio_file else ""
            enclosure = SubElement(item, "enclosure")
            enclosure.set("url", audio_url)
            enclosure.set("type", "audio/mpeg")
            if ep.file_size_bytes:
                enclosure.set("length", str(ep.file_size_bytes))

            SubElement(item, "guid").text = f"episode-{ep.pk}"
            SubElement(item, "pubDate").text = ep.created_at.strftime(f"%a, %d %b %Y %H:%M:%S {tz_offset}")

            if ep.duration_seconds:
                itunes_duration = SubElement(item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration")
                itunes_duration.text = str(ep.duration_seconds)

        return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(rss, encoding="unicode")

    @staticmethod
    def _empty_feed(request_host: str) -> str:
        """Return a valid empty RSS feed on error."""
        rss = Element("rss", version="2.0")
        channel = SubElement(rss, "channel")
        SubElement(channel, "title").text = "法穿AI · 法律故事播客"
        SubElement(channel, "link").text = request_host
        SubElement(channel, "description").text = "用街坊邻居的口吻，讲述真实的法律故事"
        SubElement(channel, "language").text = "zh-cn"
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(rss, encoding="unicode")

    @staticmethod
    def _get_timezone_offset() -> str:
        """Get the timezone offset string from Django settings."""
        try:
            import zoneinfo

            tz_name = getattr(settings, "TIME_ZONE", "Asia/Shanghai")
            tz = zoneinfo.ZoneInfo(tz_name)
            from django.utils import timezone as dj_tz

            now = dj_tz.now()
            offset = now.astimezone(tz).strftime("%z")
            if offset:
                return f"{offset[:3]}:{offset[3:]}"
        except Exception:
            logger.debug("Failed to compute timezone offset, using +08:00")
        return "+08:00"
