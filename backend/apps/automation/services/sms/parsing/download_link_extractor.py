"""Business logic services."""

import re


class DownloadLinkExtractor:
    DOWNLOAD_LINK_PATTERN = re.compile(
        r"https://zxfw\.court\.gov\.cn/zxfw/#/pagesAjkj/app/wssd/index\?"
        r"[^\s]*?(?=.*qdbh=[^\s&]+)(?=.*sdbh=[^\s&]+)(?=.*sdsin=[^\s&]+)[^\s]*",
        re.IGNORECASE,
    )
    GDEMS_LINK_PATTERN = re.compile(r"https://sd\.gdems\.com/v3/dzsd/[a-zA-Z0-9]+", re.IGNORECASE)
    JYSD_LINK_PATTERN = re.compile(r"https?://jysd\.10102368\.com/sd\?key=[^\s`,.;、】【]+", re.IGNORECASE)
    HBFY_PUBLIC_LINK_PATTERN = re.compile(r"https?://dzsd\.hbfy\.gov\.cn/hb/msg=[a-zA-Z0-9]+", re.IGNORECASE)
    HBFY_ACCOUNT_LINK_PATTERN = re.compile(r"https?://dzsd\.hbfy\.gov\.cn/sfsddz\b", re.IGNORECASE)

    def extract(self, content: str) -> list[str]:
        if not content:
            return []

        links: list[str] = []
        seen = set()

        for link in self.DOWNLOAD_LINK_PATTERN.findall(content):
            if self._is_valid(link) and link not in seen:
                links.append(link)
                seen.add(link)

        for link in self.GDEMS_LINK_PATTERN.findall(content):
            if link not in seen:
                links.append(link)
                seen.add(link)

        for raw_link in self.JYSD_LINK_PATTERN.findall(content):
            link = self._sanitize_jysd_link(raw_link)
            if link and self._is_valid(link) and link not in seen:
                links.append(link)
                seen.add(link)

        return links

    def _sanitize_jysd_link(self, link: str) -> str:
        return (link or "").strip().rstrip(".,,.;;】)")

    def _is_valid(self, link: str) -> bool:
        if "zxfw.court.gov.cn" in link:
            return all(param in link for param in ["qdbh=", "sdbh=", "sdsin="])
        if "sd.gdems.com" in link:
            return link.startswith("https://sd.gdems.com/v3/dzsd/")
        if "jysd.10102368.com" in link:
            return "key=" in link
        if "dzsd.hbfy.gov.cn/hb/msg=" in link:
            return True
        if "dzsd.hbfy.gov.cn/sfsddz" in link:
            return True
        return False
