"""佛山劳动仲裁文书爬虫（基于 Playwright，复用项目浏览器公共服务）。

设计要点：
- 列表页为服务端渲染的静态 HTML，条目形如 ``<a href=".../content/post_N.html">``。
- 详情页正文为扫描图片，需要把图片下载到本地 media。
- 增量：已存在的 detail_url 直接跳过，只爬取新条目。
- 选择器可配置（容器 / 图片），否则使用默认启发式探测，避免硬猜。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError

from apps.core.filesystem.upload_paths import DatedUUIDPath, MediaEntity
from apps.core.services.browser import create_browser
from apps.labor_arbitration.models import ArbitrationDocument, ArbitrationDocumentImage, ArbitrationDocumentSource

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})")
_PUBLISH_RE = re.compile(r"发布(?:时间|日期)[:：]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})(?:\s*(\d{1,2}[:：]\d{1,2}))?")
_CASE_NO_RE = re.compile(r"([一-龥]{1,2}劳人仲案字〔\d+〕\d+(?:-\d+)?号)")
_IMG_EXT_RE = re.compile(r"\.(png|jpe?g|bmp|tif{1,2}|webp)$", re.IGNORECASE)
_TEMPLATE_KEYWORDS = (
    "logo",
    "icon",
    "banner",
    "wechat",
    "wxgzh",
    "weixin",
    "conac",
    "jiucuo",
    "red.png",
    "nis",
    "ewm",
    "qrcode",
    "subscribe",
    "qr",
    "favicon",
    "/css/",
    "/js/",
    "arrow",
    "share",
    "top_",
    "bottom_",
)
_CONTENT_SELECTORS = [
    "#content",
    ".content",
    ".article",
    ".TRS_Editor",
    "div[class*='content']",
    "div[class*='article']",
]
# 列表页页脚导航页（带 content/post_ 但非文书），必须排除
_NAV_TITLE_KEYWORDS = (
    "联系我们",
    "隐私保护",
    "隐私",
    "免责声明",
    "免责",
    "网站地图",
    "使用帮助",
    "关于我们",
    "站点导航",
    "版权",
)


class FoshanLaborAwardCrawler:
    """佛山市人社局仲裁裁决书爬虫。"""

    def __init__(self, source: ArbitrationDocumentSource, *, limit: int | None = None) -> None:
        self.source = source
        self.limit = limit
        self.stats: dict[str, int] = {
            "discovered": 0,
            "new": 0,
            "skipped": 0,
            "failed": 0,
            "images": 0,
        }

    # ── 公共入口 ──────────────────────────────────────────────
    def crawl(self) -> dict[str, int]:
        """打开浏览器，爬取全部列表页并增量入库。"""
        with create_browser() as (page, _context):
            self._crawl_with_page(page)
        return self.stats

    def _crawl_with_page(self, page: Any) -> None:
        visited: set[str] = set()
        page_url: str | None = self.source.list_url
        page_idx = 0
        max_pages = max(self.source.max_pages, 1)
        # 详情页图片体积大（可达数 MB），浏览器内不必真正加载图片，
        # 我们只需从 DOM 读取 src，再通过 page.request.fetch 单独下载。
        page.route("**/*", self._abort_images)

        while page_url and page_idx < max_pages:
            if page_url in visited:
                break
            visited.add(page_url)
            logger.info("[劳动仲裁] 抓取列表页 %s", page_url)
            self._goto_with_retry(page, page_url)
            items = self._extract_list_items(page)
            logger.info("[劳动仲裁] 本页发现 %d 条文书", len(items))
            self.stats["discovered"] += len(items)

            for item in items:
                if self._reached_limit():
                    break
                self._handle_item(page, item)

            page_url = self._find_next_page(page, page_url, visited, page_idx + 1)
            page_idx += 1

    def _reached_limit(self) -> bool:
        if self.limit is None:
            return False
        return (self.stats["new"] + self.stats["skipped"]) >= self.limit

    def _goto_with_retry(self, page: Any, url: str, *, attempts: int = 3) -> None:
        """带指数退避的页面导航，抵御网络抖动；耗尽后抛出，交给任务层重试。"""
        last_exc: Exception | None = None
        for i in range(attempts):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                return
            except Exception as exc:
                last_exc = exc
                if i < attempts - 1:
                    wait_s = 2**i * 2  # 2s / 4s
                    logger.warning(
                        "[劳动仲裁] goto 失败 %s，%ds 后重试(%d/%d): %s",
                        url,
                        wait_s,
                        i + 1,
                        attempts,
                        exc,
                    )
                    page.wait_for_timeout(wait_s * 1000)
        assert last_exc is not None
        raise last_exc

    # ── 列表解析 ──────────────────────────────────────────────
    def _extract_list_items(self, page: Any) -> list[dict[str, Any]]:
        anchors = page.query_selector_all("a[href*='content/post_']")
        items: list[dict[str, Any]] = []
        for a in anchors:
            href = a.get_attribute("href") or ""
            if not href:
                continue
            full_url = urljoin(self.source.list_url, href)
            # 只保留本来源列表目录下的真实文书链接，排除页脚导航
            # （如 /wzdh/lxwm/content/post_*.html 的"联系我们/隐私保护/免责声明"）
            if not self._is_same_list_dir(full_url):
                continue
            raw_text = a.get_attribute("title") or a.inner_text() or ""
            text = raw_text.strip()
            if self._is_nav_title(text):
                continue
            # 列表页日期在兄弟 <span class="time"> 内（与标题不在同一节点），需读父级 <li>
            try:
                parent_text = (
                    a.evaluate(
                        "el => { const p = el.closest('li'); return p ? p.innerText : (el.parentElement ? el.parentElement.innerText : ''); }"
                    )
                    or ""
                )
            except Exception:
                parent_text = ""
            items.append(
                {
                    "url": full_url,
                    "title": self._parse_title(text),
                    "publish_date": self._parse_date(f"{text} {parent_text}"),
                }
            )

        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for it in items:
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            unique.append(it)
        return unique

    def _extract_publish_info(self, page: Any, detail_url: str) -> tuple[Any, Any]:
        """从详情页正文 meta 行解析「发布时间：YYYY-MM-DD HH:MM」。"""
        try:
            text = page.evaluate("() => document.body.innerText || ''") or ""
        except Exception:
            text = ""
        if not text:
            return None, None
        m = _PUBLISH_RE.search(text)
        if not m:
            return None, None
        date_str = m.group(1).replace("/", "-")
        time_str = (m.group(2) or "").replace("：", ":")
        try:
            if time_str:
                dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            else:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return None, None
        return dt.date(), dt

    @staticmethod
    def _is_nav_title(text: str) -> bool:
        t = text.strip()
        return any(k in t for k in _NAV_TITLE_KEYWORDS)

    @staticmethod
    def _parse_date(text: str) -> Any:
        match = _DATE_RE.search(text)
        if not match:
            return None
        try:
            from datetime import datetime

            return datetime.strptime(match.group(1).replace("/", "-"), "%Y-%m-%d").date()
        except ValueError:
            return None

    @staticmethod
    def _parse_title(text: str) -> str:
        cleaned = _DATE_RE.sub("", text).strip("[] ").strip()
        return cleaned or text.strip()

    def _find_next_page(self, page: Any, current_url: str, visited: set[str], current_page_no: int) -> str | None:
        next_labels = ("下一页", "下页", "下一頁")
        # 优先「下一页」
        for a in page.query_selector_all("a"):
            label = (a.inner_text() or "").strip()
            href = a.get_attribute("href") or ""
            if not href:
                continue
            abs_href = urljoin(current_url, href)
            if abs_href in visited:
                continue
            if label in next_labels and self._is_same_list_dir(abs_href):
                return abs_href
        # 退而求其次：页码严格大于当前页
        for a in page.query_selector_all("a"):
            label = (a.inner_text() or "").strip()
            href = a.get_attribute("href") or ""
            if not href or not label.isdigit() or int(label) <= current_page_no:
                continue
            abs_href = urljoin(current_url, href)
            if abs_href in visited:
                continue
            if self._is_same_list_dir(abs_href):
                return abs_href
        return None

    def _is_same_list_dir(self, url: str) -> bool:
        base = urlparse(self.source.list_url)
        cur = urlparse(url)
        prefix = base.path if base.path.endswith("/") else base.path + "/"
        return base.netloc == cur.netloc and cur.path.startswith(prefix)

    # ── 单条处理 ───────────────────────────────────────────────
    def _handle_item(self, page: Any, item: dict[str, Any]) -> None:
        url = item["url"]
        if ArbitrationDocument.objects.filter(detail_url=url).exists():
            self.stats["skipped"] += 1
            # 回填：已存在记录缺发布日期时，用本次列表页解析到的日期补上（不重下图片）
            if item["publish_date"] is not None:
                ArbitrationDocument.objects.filter(detail_url=url, publish_date__isnull=True).update(
                    publish_date=item["publish_date"]
                )
            return
        try:
            self._crawl_detail(page, item)
            self.stats["new"] += 1
        except IntegrityError:
            # 并发：另一任务已插入同 detail_url，视为已爬取，跳过
            self.stats["skipped"] += 1
        except Exception as exc:
            logger.error("[劳动仲裁] 抓取详情失败 %s: %s", url, exc, exc_info=True)
            self.stats["failed"] += 1
            try:
                ArbitrationDocument.objects.create(
                    source=self.source,
                    title=item["title"],
                    detail_url=url,
                    publish_date=item["publish_date"],
                    crawl_status="failed",
                    error_message=str(exc)[:2000],
                )
            except IntegrityError:
                # 并发下 failed 记录也可能撞唯一约束，忽略
                pass

    def _crawl_detail(self, page: Any, item: dict[str, Any]) -> ArbitrationDocument:
        url = item["url"]
        logger.info("[劳动仲裁] 抓取详情 %s", url)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self._trigger_lazy_images(page)

        img_urls = self._extract_image_urls(page, url)
        if not img_urls:
            raise RuntimeError("详情页未找到任何图片")

        # 发布时间优先取详情页正文 meta（含时分），列表页日期作为兜底
        pdate, pdt = self._extract_publish_info(page, url)
        publish_date = pdate or item["publish_date"]

        doc = ArbitrationDocument.objects.create(
            source=self.source,
            title=item["title"],
            case_number=self._parse_case_number(item["title"]),
            detail_url=url,
            publish_date=publish_date,
            publish_datetime=pdt,
            crawl_status="success",
        )
        for idx, img_url in enumerate(img_urls):
            self._download_image(page, doc, img_url, idx)
        return doc

    @staticmethod
    def _parse_case_number(title: str) -> str:
        match = _CASE_NO_RE.search(title)
        return match.group(1) if match else ""

    def _trigger_lazy_images(self, page: Any) -> None:
        """滚动页面以触发懒加载图片。"""
        try:
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
        except Exception as exc:  # pragma: no cover
            logger.debug("[劳动仲裁] 触发懒加载失败（忽略）: %s", exc)

    # ── 图片提取与下载 ────────────────────────────────────────
    def _extract_image_urls(self, page: Any, detail_url: str) -> list[str]:
        container_sel = self.source.detail_image_container_selector.strip()
        base_imgs = None
        if container_sel:
            container = page.query_selector(container_sel)
            if container is not None:
                base_imgs = container.query_selector_all(self.source.detail_image_selector.strip() or "img")

        if base_imgs is None:
            for sel in _CONTENT_SELECTORS:
                container = page.query_selector(sel)
                if container is not None:
                    found = container.query_selector_all("img")
                    if found:
                        base_imgs = found
                        break

        if base_imgs is None:
            base_imgs = page.query_selector_all("img")

        result: list[str] = []
        seen: set[str] = set()
        for img in base_imgs:
            src = (
                img.get_attribute("src") or img.get_attribute("data-src") or img.get_attribute("data-original") or ""
            ).strip()
            if not src:
                continue
            abs_url = urljoin(detail_url, src)
            # 仅保留同源图片（政府站点文档扫描件与列表同域；站外徽标/二维码丢弃）
            if not self._is_same_host(abs_url):
                continue
            if not _IMG_EXT_RE.search(abs_url):
                low = abs_url.lower()
                if any(k in low for k in ("logo", "icon", "banner")):
                    continue
            if self._is_template_asset(abs_url):
                continue
            if abs_url in seen:
                continue
            seen.add(abs_url)
            result.append(abs_url)
        return result

    def _is_same_host(self, url: str) -> bool:
        """图片必须与来源同域（含子域），丢弃站外模板资源。"""
        base = urlparse(self.source.list_url).netloc
        cur = urlparse(url).netloc
        return cur == base or cur.endswith("." + base)

    @staticmethod
    def _is_template_asset(url: str) -> bool:
        low = url.lower()
        return any(k in low for k in _TEMPLATE_KEYWORDS)

    @staticmethod
    def _abort_images(route: Any, request: Any) -> None:
        """拦截图片资源加载，加速详情页导航（图片仍经 request.fetch 单独下载）。"""
        try:
            if request.resource_type == "image":
                route.abort()
            else:
                route.continue_()
        except Exception:
            pass

    def _download_image(
        self, page: Any, doc: ArbitrationDocument, img_url: str, idx: int
    ) -> ArbitrationDocumentImage | None:
        # 政府站点扫描件体积大（可达数 MB），慢链路下需更长超时并允许重试。
        data: bytes | None = None
        last_err = "unknown"
        for attempt in range(2):
            try:
                resp = page.request.fetch(img_url, method="GET", timeout=90000)
                if resp.status >= 400:
                    last_err = f"HTTP {resp.status}"
                    continue
                body = resp.body()
                if not body:
                    last_err = "empty body"
                    continue
                data = body
                break
            except Exception as exc:
                last_err = str(exc)
        if not data:
            logger.warning("[劳动仲裁] 图片下载失败 %s: %s", img_url, last_err)
            return None

        ext = self._guess_ext(img_url, data)
        filename = f"page_{idx:03d}{ext}"
        rel_path = DatedUUIDPath(MediaEntity.LABOR_ARBITRATION_DOCS)(None, filename)
        saved_name = default_storage.save(rel_path, ContentFile(data))
        img = ArbitrationDocumentImage.objects.create(
            document=doc,
            image=saved_name,
            page_index=idx,
            source_url=img_url,
            file_size=len(data),
        )
        self.stats["images"] += 1
        return img

    @staticmethod
    def _guess_ext(url: str, data: bytes) -> str:
        match = _IMG_EXT_RE.search(url)
        if match:
            return "." + match.group(1).lower()
        if data[:3] == b"\xff\xd8\xff":
            return ".jpg"
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return ".png"
        if data[:2] == b"BM":
            return ".bmp"
        if data[:4] in (b"II*\x00", b"MM\x00*"):
            return ".tif"
        return ".jpg"
