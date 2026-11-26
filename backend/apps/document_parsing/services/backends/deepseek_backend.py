"""DeepSeek OCR 后端（``POST https://api.deepseek.com/v1/tools/ocr``）。

## 为什么会有这个后端

它解决的问题是「**读得准**」：真实扫描卷宗里旋转页（90°/180°）会被 MinerU 读成
行序反转 + 错字密集的正文（实测同一页上人名、律所名、`一审程序` 三处都被认错），
而 DeepSeek 对同一批页读得对。代价是它会**概率性地整页崩掉**。

所以本后端自己带一层修补，不把烂页丢给下游：

```
整份（或本批）→ 主 purpose（默认 text_recognition）  1 次调用
  ↓ 页级退化检测（page_degeneracy：空 / 同一行重复 / 窗口去重比 / 截断且重复）
  ↓ 退化页逐页单独重试（并发 4，约 2.5s/页）：
  ↓   复读类 → 换成与主 purpose 相反的那种
  ↓   空返回 → 先原样重试（瞬时故障），仍空再换 purpose
  ↓ 仍退化 → 清空正文返回（上层按 pending 页走 MinerU 接力 / 本地 OCR）
```

实测（三份卷宗，37 / 93 / 164 页）：首跑硬退化 10.8% / 5.4% / 22.6%；
单页换 purpose 重试能救 **65%–71%** 的残余。空返回是瞬时的（164 页上 11 页空返回
重试一次 11/11 全恢复），复读是半瞬时的。

## 两种 purpose 的产物形态不一样（这是本后端最需要小心的地方）

| purpose | 有正文 | 有坐标 | 形态 |
|---|---|---|---|
| ``text_recognition`` | ✅ | ❌ | Markdown 风格：``#`` 标题层级 + ``<table border=1>`` HTML 表格 |
| ``rich_layout_recognition`` | ✅ | ✅ | 标记流：``〈｜ref｜〉〈｜title｜〉〈｜box｜〉[[x1,y1,x2,y2]]…`` |

- 标记分隔符是**全角竖线 U+FF5C**，不是 ASCII ``|``——按文档里的半角写法写正则会
  一条都匹配不到。
- 坐标是**千分比**（0–1000，原点左上），与 MinerU 同量纲。所以 ``bbox.resolve_bbox_unit``
  里 ``deepseek`` 归 ``permille``。
- 坐标是**原始页帧**下的：一页 90° 旋转扫描的正文，框是「窄高」的。别拿「宽>高」
  判断坐标轴反了——那会把对的判成错的。

## 凭证放哪

``SystemConfig`` 的 ``DEEPSEEK_OCR_API_KEY``（默认配置项在
``apps/core/admin/_system_config_data/_service_configs.py`` 的 ``get_ocr_configs``）。
与 MinerU / Textin 走 ``DocumentParseProvider`` 不同：那两个是多平台多渠道的供应商，
DeepSeek OCR 是单一渠道，放 SystemConfig 少一层配置面。
"""

from __future__ import annotations

import logging
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

from apps.document_parsing.exceptions.parsing_exceptions import DocumentParsingError
from apps.document_parsing.protocols.document_parser_protocol import (
    BLOCK_TYPE_IMAGE,
    ParseCoverage,
    ParsedBlock,
    ParsedDocument,
    normalize_block_type,
)
from apps.pdf_splitting.services.split.page_degeneracy import degeneracy_reason

logger = logging.getLogger(__name__)

#: 已确认可在生产使用的 purpose 取值。
PURPOSE_TEXT = "text_recognition"
PURPOSE_RICH = "rich_layout_recognition"

#: 单页修补的并发上限。账号级限制是「同时 15 个文档上传」，留足余量给其它并发任务
#: （材料预处理常常同时在跑好几份材料）。
_REPAIR_WORKERS = 4

#: 一次 HTTP 调用的超时。官方限制：上传 120s、解析 120s，总时长按 180s 设计；
#: 留到 300s 是因为 164 页/66 MiB 这种体积在本机实测要 15–30s，但弱网下上传会吃满。
_REQUEST_TIMEOUT = 300.0

#: 网关真实上限。官方文档写 100 MiB，**实测 66 MiB 的文件直接 413**
#: （openresty 挡在前面，返回 HTML 而不是 JSON）。这里按 48 MiB 预判并给出可操作的错误，
#: 让分流层提前拆批，而不是等云端回一个看不懂的 HTML。
_MAX_UPLOAD_BYTES = 48 * 1024 * 1024

#: rich 模式的块标记。**真实语法与官方文档描述的不一样**，按实测（2026-11-25）：
#:
#:     〈｜ref｜〉image〈｜/ref｜〉〈｜box｜〉[[213,0,999,999]]〈｜/box｜〉
#:       └ 开标记 ┘ 类型 └ 闭标记 ┘ └ 开 ┘   四点坐标（千分比）   └ 闭 ┘
#:
#: 三处容易写错、写错就一条都匹配不到：
#: 1. 分隔符是**全角竖线 U+FF5C**，不是 ASCII ``|``；
#: 2. 块类型词夹在 ``ref`` 与 ``/ref`` 两个标签**之间**（不是标签里）；
#: 3. 坐标在 ``box`` 那一对标签里，且在类型之后。
#: 块的正文从闭标记之后开始，直到下一个开标记。
#:
#: 另有一个只剥「版面标记」、**不碰 HTML** 的剥法（``_strip_layout_markers``）：
#: text 模式的表格正文本身就是 ``<table border=1>`` 这种 HTML，用通用去标签函数
#: 会把表格结构一起铲平。两种模式要分别处理。
_MARKER_RE = re.compile(
    r"<\uFF5Cref\uFF5C>(?P<type>[a-zA-Z_]+)<\uFF5C/ref\uFF5C>\s*"
    r"<\uFF5Cbox\uFF5C>\s*"
    r"\[\[\s*(?P<x1>-?\d+)\s*,\s*(?P<y1>-?\d+)\s*,\s*(?P<x2>-?\d+)\s*,\s*(?P<y2>-?\d+)\s*\]\]\s*"
    r"<\uFF5C/box\uFF5C>"
)


def _extract_single_page(path: Path, page_no: int) -> Path:
    """抽单页成临时 PDF。``page_no`` 是 1 起的页号。

    放模块级而不是塞进类里：服务层禁用静态方法装饰器
    （`tests/ci/structure/test_four_layer_architecture.py` 的结构棘轮按装饰器计数，
    连注释里出现那个写法都会被计一次），而这个函数本来也不碰任何实例状态——
    提出来比硬塞进类里更诚实。
    """
    import pymupdf as fitz

    document = fitz.open(str(path))
    single = fitz.open()
    try:
        single.insert_pdf(document, from_page=page_no - 1, to_page=page_no - 1)
        with tempfile.NamedTemporaryFile(suffix=".pdf", prefix=f"ds_p{page_no}_", delete=False) as handle:
            temp_name = handle.name
        single.save(temp_name)
        return Path(temp_name)
    finally:
        single.close()
        document.close()


class DeepSeekOCRBackend:
    """DeepSeek OCR 云端引擎（见模块头注释）。"""

    provider_type: str = "deepseek"

    #: 云端 HTTP 调用，阻塞时间可达分钟级：走异步执行而不是占住请求线程。
    requires_async_execution: bool = True

    #: 能力位：正文一定拿得到；坐标只有 ``rich_layout_recognition`` 才有，
    #: 而本后端默认用 text 模式（只为退化页换 rich 重试），所以 ``has_bbox`` 声明为 True
    #: 但**逐页**可能没有 blocks——调用方按 ``layout.pages[].blocks`` 是否为空判断，
    #: 不要拿文档级能力位当逐页保证。
    coverage = ParseCoverage(has_blocks=True, has_bbox=True, has_confidence=False, has_page_geometry=False)

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = _REQUEST_TIMEOUT,
        purpose: str | None = None,
        max_repair_pages: int = 64,
        **kwargs: Any,
    ) -> None:
        self._explicit_key = api_key
        self.timeout = timeout
        self._purpose_override = purpose
        self._max_repair_pages = max(0, int(max_repair_pages))
        self.api_url = str(kwargs.pop("api_url", "") or "").strip()

    # ---------- 配置 ----------

    def _config(self, key: str, default: str = "") -> str:
        from apps.core.services.system_config_service import SystemConfigService

        return str(SystemConfigService().get_value(key, default) or "").strip()

    @property
    def api_key(self) -> str:
        return self._explicit_key or self._config("DEEPSEEK_OCR_API_KEY")

    @property
    def endpoint(self) -> str:
        return self.api_url or self._config("DEEPSEEK_OCR_API_URL", "https://api.deepseek.com/v1/tools/ocr")

    @property
    def purpose(self) -> str:
        """主 purpose：默认 text（快、便宜、正文最干净）；配成 rich 时整本带坐标。"""
        chosen = self._purpose_override or self._config("DEEPSEEK_OCR_PURPOSE", PURPOSE_TEXT)
        chosen = chosen.lower()
        return chosen if chosen in (PURPOSE_TEXT, PURPOSE_RICH) else PURPOSE_TEXT

    def _is_configured(self) -> bool:
        return bool(self.api_key and self.endpoint)

    # ---------- 主入口 ----------

    def parse_document(
        self,
        file_path: str,
        file_type: str = "pdf",
        extract_tables: bool = True,
        extract_images: bool = False,
        return_markdown: bool = False,
        **kwargs: Any,
    ) -> ParsedDocument:
        """解析文档：主调用 + 退化页单页修补。

        Args:
            file_path: 本地文件路径。
            file_type: 文件类型（本后端按 PDF 处理，其它类型同样直接上传）。
            extract_tables / extract_images / return_markdown: 与其它后端保持同签名，
                本后端恒按「拿全部正文与表格」处理，不按这几个开关裁剪。
        """
        path = Path(file_path)
        if not path.exists():
            raise DocumentParsingError(f"文件不存在: {file_path}")
        if not self._is_configured():
            raise DocumentParsingError("DeepSeek OCR 未配置：请在系统配置里填写 DEEPSEEK_OCR_API_KEY")
        size = path.stat().st_size
        if size > _MAX_UPLOAD_BYTES:
            # 官方写 100 MiB，实测 66 MiB 就 413（openresty 挡的）。提前给可读原因，
            # 而不是让上层拿到一坨 HTML。
            raise DocumentParsingError(
                f"文件过大: {size / 1024 / 1024:.1f} MiB（DeepSeek OCR 网关实测上限约 48 MiB，"
                f"官方文档写的 100 MiB 不可信）。请先按页拆分后再解析。"
            )

        started = time.monotonic()
        result = self._call_ocr(path, self.purpose)
        pages: dict[int, str] = {
            int(item["index"]) + 1: str(item.get("text") or "") for item in result.get("pages", [])
        }
        finishes: dict[int, str] = {
            int(item["index"]) + 1: str(item.get("finish_reason") or "") for item in result.get("pages", [])
        }

        repairs = self._repair_degenerate_pages(path, pages, finishes) if self._max_repair_pages else {}
        # 修补后仍然退化的页：**必须清空正文**，不能原样交出去。
        #
        # 原样返回的后果是「假成功」：这一页有字（是复读的垃圾），上层就不会把它当
        # pending 页去走 MinerU / 本地 OCR，于是 17000 字的复读正文一路进 Markdown、
        # 进分段、进归案。实测 617 的 p1 就是这样（修补后 rich 只回「整页一张图」）。
        # 清空后 `ocr_handler` 会把它记成 `<backend>_empty` → 进 pending → 走兜底。
        #
        # **修好的页不再复判**：它们在 `_retry_single_page` 里已按**重试那次自己的**
        # finish_reason 判过一次。这里若拿首跑遗留的 `finish_reason="length"` 去判修好的
        # 正文，「截断 + 唯一行 <0.5」那条会把一份正常的勾选表单（大量短行 `☐是 ☐否`）
        # 当成循环清空——修好了又被自己清掉。
        unrepaired = {
            page_no: reason
            for page_no, text in sorted(pages.items())
            if page_no not in repairs and (reason := degeneracy_reason(text, finishes.get(page_no)))
        }
        for page_no in unrepaired:
            pages[page_no] = ""
        if unrepaired:
            logger.warning(
                "DeepSeek OCR 修补后仍有 %d 页退化，已清空正文交上层兜底: %s",
                len(unrepaired),
                unrepaired,
            )

        layout = self._build_layout(pages)
        # 顶层 ``text`` 从 ``layout["pages"]`` 拼，不从 ``pages`` 拼：后者是未剥标记的
        # rich 原文，非 pdf_splitting 调用方（只读 ``parsed.text``）会拿到裸
        # ``〈｜ref｜〉`` 与 ``[[x,y,x,y]]``。layout 里每页已过 ``_strip_layout_markers``
        # （只剥版面标记、保留 ``<table>`` HTML），text 模式的正文本来就没有标记。
        text = "\n\n".join(str(page_entry.get("text") or "") for page_entry in layout["pages"])
        elapsed = round(time.monotonic() - started, 2)
        logger.info(
            "DeepSeek OCR 完成: %s (%s 页, %s, %.2fs, 修补 %d 页)",
            path.name,
            len(pages),
            self.purpose,
            elapsed,
            len(repairs),
        )
        return ParsedDocument(
            text=text,
            parse_method="deepseek",
            layout=layout,
            blocks=_to_parsed_blocks(layout),
            coverage=self.coverage,
            metadata={
                "page_count": len(pages),
                "purpose": self.purpose,
                "elapsed_seconds": elapsed,
                "repaired_pages": sorted(repairs),
                # 每个修好的页用的是哪种 purpose：rich 修好的页带坐标、text 修好的页没有，
                # 「这页为什么没绿框」要能从这里查到。
                "repair_purposes": dict(sorted(repairs.items())),
                "unrepaired_pages": unrepaired,
                "usage": result.get("usage") or {},
            },
        )

    # ---------- 单次 OCR 调用 ----------

    def _call_ocr(self, path: Path, purpose: str) -> dict[str, Any]:
        """一次 multipart 调用。``purpose`` 必须排在 ``file`` 之前（官方明确要求）。"""
        try:
            with httpx.Client(timeout=self.timeout) as client, path.open("rb") as handle:
                response = client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data={"purpose": purpose},
                    files={"file": (path.name, handle, "application/octet-stream")},
                )
        except httpx.HTTPError as exc:
            raise DocumentParsingError(f"DeepSeek OCR 请求失败: {exc}") from exc

        if response.status_code != 200:
            raise DocumentParsingError(f"DeepSeek OCR 返回 {response.status_code}: {response.text[:200]}")
        # 识别失败/超时时返回体不是结果而是 {"error": {...}}，状态码仍是 200。
        try:
            payload = response.json()
        except ValueError as exc:
            raise DocumentParsingError(f"DeepSeek OCR 返回非 JSON: {response.text[:200]}") from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise DocumentParsingError(f"DeepSeek OCR 识别失败: {payload['error']}")
        return payload if isinstance(payload, dict) else {}

    # ---------- 退化页修补 ----------

    def _repair_degenerate_pages(
        self,
        path: Path,
        pages: dict[int, str],
        finishes: dict[int, str],
    ) -> dict[int, str]:
        """对退化页逐页单独重试（purpose 顺序见 ``_retry_purposes``），成功就替换正文。

        换 purpose 而不是原样重试：实测复读页里相当一部分换 purpose 后能读对
        （617 的 p8/p33 都是 text→rich 救回来的），而原样重试对这类页成功率明显低。

        Returns:
            ``{页号: 修好那次用的 purpose}``；``pages`` 被**原地**替换成修好的正文。
            没修好的页不在表里（上层按 pending 页处理）。
        """
        targets = {
            page_no: reason
            for page_no, text in sorted(pages.items())
            if (reason := degeneracy_reason(text, finishes.get(page_no)))
        }
        targets = dict(list(targets.items())[: self._max_repair_pages])
        if not targets:
            return {}

        repaired: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=_REPAIR_WORKERS) as pool:
            futures = {
                page_no: pool.submit(self._retry_single_page, path, page_no, self._retry_purposes(reason))
                for page_no, reason in targets.items()
            }
            for page_no, future in futures.items():
                outcome = future.result()
                if outcome is None:
                    continue
                pages[page_no], repaired[page_no] = outcome

        failed = [page_no for page_no in targets if page_no not in repaired]
        logger.info(
            "DeepSeek OCR 退化页修补: %d/%d 修好%s",
            len(repaired),
            len(targets),
            f"，仍坏 {failed}" if failed else "",
        )
        return repaired

    def _retry_purposes(self, reason: str) -> list[str]:
        """单页重试依次用哪些 purpose。

        - 一律包含「与主调用**相反**的 purpose」：主调用是 text 就换 rich，主调用是 rich
          就换 text。写死 rich 的后果是主调用已是 rich 时重试只是原样再来一遍。
        - **空返回**先按主 purpose 原样重试一次：空返回是瞬时故障（164 页上 11 页空返回，
          原样重试 11/11 恢复），原样重试还能让这页的产物形态与全书一致；仍不行再换。
        """
        primary = self.purpose
        alternate = PURPOSE_RICH if primary == PURPOSE_TEXT else PURPOSE_TEXT
        if reason == "空返回":
            return [primary, alternate]
        return [alternate]

    def _retry_single_page(self, path: Path, page_no: int, purposes: list[str]) -> tuple[str, str] | None:
        """把第 ``page_no`` 页单独抽成 PDF，按 ``purposes`` 依次重试。

        Returns:
            ``(正文, 用的 purpose)``；全部仍退化返回 None。
        """
        try:
            mini = _extract_single_page(path, page_no)
        except (OSError, RuntimeError, ValueError) as exc:  # pragma: no cover - 抽页失败极少见，但要留痕
            logger.warning("DeepSeek OCR 单页抽取失败 page=%s: %s", page_no, exc)
            return None
        try:
            for purpose in purposes:
                text = self._retry_once(mini, page_no, purpose)
                if text is not None:
                    return text, purpose
            return None
        finally:
            mini.unlink(missing_ok=True)

    def _retry_once(self, mini: Path, page_no: int, purpose: str) -> str | None:
        """单页单次调用；拿到可用正文返回它，否则 None（失败原因留痕）。"""
        try:
            payload = self._call_ocr(mini, purpose)
        except DocumentParsingError as exc:
            logger.warning("DeepSeek OCR 单页重试失败 page=%s purpose=%s: %s", page_no, purpose, exc)
            return None
        items = payload.get("pages") or []
        if not items:
            return None
        text = str(items[0].get("text") or "")
        reason = degeneracy_reason(text, str(items[0].get("finish_reason") or ""))
        if reason:
            logger.info("DeepSeek OCR 单页重试仍退化 page=%s purpose=%s: %s", page_no, purpose, reason)
            return None
        return text

    # ---------- 版面 ----------

    def _build_layout(self, pages: dict[int, str]) -> dict[str, Any]:
        """把逐页正文组装成 ``{"page_count", "pages":[{page_no, text, blocks}]}``。

        ``blocks`` 按**这一页正文里有没有 rich 标记**决定，而不是按「是不是修补页」：
        主 purpose 配成 rich 时全书每页都带坐标，按修补页判会把未修补页的坐标全丢掉。
        text 模式的正文没有标记，``_parse_rich_blocks`` 自然返回空——不会凭空造块
        （凭空造块只会让「原文坐标对照」指到错的地方）。
        """
        page_entries: list[dict[str, Any]] = []
        for page_no, text in sorted(pages.items()):
            blocks = _parse_rich_blocks(text)
            page_entries.append(
                {
                    "page_no": page_no,
                    # 两种模式的正文都要剥版面标记（text 模式本来就没有，剥了是 no-op）；
                    # 只剥标记、不剥 HTML——表格正文就靠 HTML 表达结构。
                    "text": _strip_layout_markers(text),
                    "blocks": blocks,
                }
            )
        return {"page_count": len(page_entries), "pages": page_entries, "page_index_base": 1}


#: 整个标记构造（含夹在 ref 标签**之间**的块类型词）。只剥标签不剥类型词，
#: 正文里就会残留 `image` / `title` 这些英文单词——它们不是正文。
_LAYOUT_MARKER_RE = re.compile(
    r"<\uFF5Cref\uFF5C>[a-zA-Z_]*(?:<\uFF5C/ref\uFF5C>)?\s*"
    r"(?:<\uFF5Cbox\uFF5C>)?\s*(?:\[\[[^\]]*\]\])?\s*(?:<\uFF5C/box\uFF5C>)?"
)
_LAYOUT_COORD_RE = re.compile(r"\[\[\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*\]\]")


def _strip_layout_markers(text: str) -> str:
    """只剥 rich 模式的版面标记与坐标，**保留 HTML**。

    与 ``page_degeneracy.strip_cloud_markers`` 的区别：那个用于「这页还有没有正文」的
    计数，所以连 HTML 标签一起铲；这里产出的正文要给下游建 Markdown，铲掉
    ``<table>`` 会把表格结构毁掉。
    """
    return _LAYOUT_COORD_RE.sub(" ", _LAYOUT_MARKER_RE.sub(" ", text or "")).strip()


def _parse_rich_blocks(text: str) -> list[dict[str, Any]]:
    """把 rich 模式的标记流拆成 ``[{type, text, bbox}]``（bbox 为千分比四点）。

    标记之间的内容就是该块的正文；没有标记的前导内容丢掉——那正是「无坐标的文字」，
    硬塞进块里会让块级定位错位。
    """
    matches = list(_MARKER_RE.finditer(text or ""))
    blocks: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = (text or "")[start:end].strip()
        block_type = normalize_block_type(match.group("type"))
        # ``image`` 块标记后通常**没有正文**（整页照片的如实自述，实测 4/4 都是空 body）。
        # 空 body 就丢的后果：``page_quality.rescue_image_region`` 的触发条件正是
        # 「``type=="image"`` 且 ``text==""`` 且有 ``bbox``」，永远凑不齐 → 图片页
        # 补救整条断路。所以只对 image 放行空 body，其余类型照旧跳过。
        if not body and block_type != BLOCK_TYPE_IMAGE:
            continue
        blocks.append(
            {
                "type": block_type,
                "text": body,
                "bbox": [
                    float(match.group("x1")),
                    float(match.group("y1")),
                    float(match.group("x2")),
                    float(match.group("y2")),
                ],
            }
        )
    return blocks


def _to_parsed_blocks(layout: dict[str, Any]) -> list[ParsedBlock]:
    """``layout`` → 扁平块列表（跨页顺序）。给块级质检/复核用。"""
    blocks: list[ParsedBlock] = []
    for page in layout.get("pages") or []:
        for block in page.get("blocks") or []:
            blocks.append(
                ParsedBlock(
                    type=str(block.get("type") or "text"),
                    text=str(block.get("text") or ""),
                    bbox=block.get("bbox"),
                    page_no=int(page.get("page_no") or 0) or None,
                )
            )
    return blocks
