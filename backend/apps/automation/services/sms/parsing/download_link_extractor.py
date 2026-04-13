"""Business logic services."""

import re
from urllib.parse import parse_qs, urlparse


class DownloadLinkExtractor:
    DOWNLOAD_LINK_PATTERN = re.compile(
        r"https?://[^\s/]+/zxfw/#/pagesAjkj/app/wssd/index\?"
        r"[^\s]*?(?=.*qdbh=[^\s&]+)(?=.*sdbh=[^\s&]+)(?=.*sdsin=[^\s&]+)[^\s]*",
        re.IGNORECASE,
    )
    GDEMS_LINK_PATTERN = re.compile(r"https?://[^\s/]+/v3/dzsd/[a-zA-Z0-9]+", re.IGNORECASE)
    JYSD_LINK_PATTERN = re.compile(r"https?://[^\s/]+/sd\?key=[^\s`,.;、】【]+", re.IGNORECASE)
    HBFY_PUBLIC_LINK_PATTERN = re.compile(r"https?://[^\s/]+/hb/msg=[a-zA-Z0-9]+", re.IGNORECASE)
    HBFY_ACCOUNT_LINK_PATTERN = re.compile(r"https?://[^\s/]+/sfsddz\b", re.IGNORECASE)
    SFDW_LINK_PATTERN = re.compile(r"https?://[^\s/]+/sfsdw//r/[a-zA-Z0-9]+", re.IGNORECASE)
    URL_CANDIDATE_PATTERN = re.compile(r"https?://[^\s<>'\"，。；;]+", re.IGNORECASE)

    def extract(self, content: str) -> list[str]:
        if not content:
            return []

        links: list[str] = []
        seen = set()

        candidates: list[str] = []
        candidates.extend(self.DOWNLOAD_LINK_PATTERN.findall(content))
        candidates.extend(self.GDEMS_LINK_PATTERN.findall(content))
        candidates.extend(self.JYSD_LINK_PATTERN.findall(content))
        candidates.extend(self.HBFY_PUBLIC_LINK_PATTERN.findall(content))
        candidates.extend(self.HBFY_ACCOUNT_LINK_PATTERN.findall(content))
        candidates.extend(self.SFDW_LINK_PATTERN.findall(content))
        candidates.extend(self.URL_CANDIDATE_PATTERN.findall(content))

        for raw_link in candidates:
            link = self._sanitize_link(raw_link)
            if not link or link in seen:
                continue
            if self._is_valid(link):
                links.append(link)
                seen.add(link)

        return links

    def _sanitize_link(self, link: str) -> str:
        trailing_chars = ".,;:，。；：!！?？)）]】\"'“”"
        return (link or "").strip().rstrip(trailing_chars)

    def _is_valid(self, link: str) -> bool:
        link_lower = link.lower()
        parsed = urlparse(link)
        path_lower = parsed.path.lower()
        query_params = parse_qs(parsed.query)

        if "/zxfw/#/pagesajkj/app/wssd/index" in link_lower:
            return all(param in link_lower for param in ["qdbh=", "sdbh=", "sdsin="])

        if "/v3/dzsd/" in path_lower:
            return True

        if path_lower.endswith("/sd") and "key" in query_params:
            return True

        if path_lower.endswith("/hb/msg") and "msg" in query_params:
            return True
        if path_lower.endswith("/sfsddz"):
            return True

        if "/sfsdw//r/" in path_lower:
            return True

        return False
