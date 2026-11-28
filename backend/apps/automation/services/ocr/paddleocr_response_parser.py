"""PaddleOCR 响应解析层（从 ``paddleocr_api_service`` 拆分出来，2026-11-27）。

纯解析，无 HTTP、无 IO：

- 模型键归一与模型分类型集合（哪个模型吃哪种响应信封）；
- ``PaddleOCRApiResult`` / ``ParsedTableResult`` / ``ParsedPageOrientation`` /
  ``PaddleOCRApiImage`` 四个结果数据类；
- HTML 表格 → GFM、``markdown["images"]`` 收集；
- PP-StructureV3 表格几何（``layoutParsingResults[].prunedResult.table_res_list``）
  与逐页方向分类（``doc_preprocessor_res``）的解析入口。

依赖方向单向：``paddleocr_api_service`` → 本模块。本模块**不得** import
``paddleocr_api_service``（会成环），也不依赖 httpx / Django。解析一律不抛：
一次付费调用的结果不能因为一条脏数据作废，跳过与留痕都由这里负责。
"""

from __future__ import annotations

import html
import json
import logging
import math
import re
from dataclasses import dataclass, field, replace
from typing import Any

logger = logging.getLogger(__name__)

# 配置里存的模型键 → PaddleOCR 服务端要求的模型名。
#
# ⚠️ 这两者**必须**区分开，否则线上直接报「模型传参错误」(code=10007)：
# 服务端只认 `PaddleOCR-VL-1.6` 这种带大写的官方模型名，而配置里长期沿用
# `paddleocr_vl_1_6` 这类小写下划线键（历史命名，改动会动到已落库的配置值）。
# 所以映射只放在发送前这一处，配置侧保持原键不变。
_MODEL_API_NAME_MAP: dict[str, str] = {
    "pp_ocrv5": "PP-OCRv5",
    "pp_ocrv6": "PP-OCRv6",
    "pp_structure_v3": "PP-StructureV3",
    "paddleocr_vl": "PaddleOCR-VL",
    "paddleocr_vl_1_5": "PaddleOCR-VL-1.5",
    "paddleocr_vl_1_6": "PaddleOCR-VL-1.6",
}

# 历史库里混存过两种写法：小写下划线键（paddleocr_vl_1_6）与官方名
# （PaddleOCR-VL-1.6 / PP-OCRv6）。两者都要能识别，否则老数据会掉进
# 「不支持的 PaddleOCR 模型」分支或发错名字。归一化函数把两者统一到小写键。


def _collect_markdown_images(raw_images: Any) -> list[PaddleOCRApiImage]:
    """把 ``markdown["images"]``（相对路径 → 绝对 URL）转成 ``PaddleOCRApiImage`` 列表。

    markdown 正文里的 ``<img src="imgs/xxx.jpg">`` 是死链（相对路径没有宿主），
    真实可下载地址只存在于这个映射里。所以这里把 URL 单独收出来，正文里就不用
    再带链接了——顺便避免 URL 污染 raw_texts。

    非 dict 或 key/value 不成立的脏数据直接跳过：宁可少几张图，不能让一条坏数据
    让整个识别任务抛异常。
    """
    if not isinstance(raw_images, dict):
        return []

    images: list[PaddleOCRApiImage] = []
    seen: set[str] = set()
    for key, url in raw_images.items():
        image_key = str(key or "").strip()
        image_url = str(url or "").strip()
        if not image_key or not image_url or image_key in seen:
            continue
        seen.add(image_key)
        images.append(PaddleOCRApiImage(key=image_key, url=image_url, data=None))
    return images


# HTML 表格 → GFM 表格的正则组。
# 用正则而非 BeautifulSoup：本模块只被 OCR 解析路径依赖，引入 HTML 解析器
# 等于为一个辅助函数加一层运行时依赖；PaddleOCR-VL 输出的表格结构是固定的
# `<table><tr><td ...>…</td></tr></table>`，正则足够且不引入新依赖。
_TABLE_RE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)
_TR_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
# 单独捕获标签名与属性串，才能读出 colspan / rowspan
_CELL_RE = re.compile(r"<t([dh])\b([^>]*)>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_COLSPAN_RE = re.compile(r"colspan\s*=\s*[\"']?(\d+)", re.IGNORECASE)
_ROWSPAN_RE = re.compile(r"rowspan\s*=\s*[\"']?(\d+)", re.IGNORECASE)


def _span_value(pattern: re.Pattern[str], attrs: str) -> int:
    """从标签属性串取 colspan/rowspan；缺失或非法按 1 处理（尽力而为）。"""
    match = pattern.search(attrs or "")
    if not match:
        return 1
    try:
        return max(1, int(match.group(1)))
    except (TypeError, ValueError):
        return 1


def _cell_text(inner: str) -> str:
    """单元格 HTML 片段 → GFM 单元内容。

    顺序很关键：
    1. ``<br>`` 先换成空格 —— 直接去标签会把上下两行粘成一个词；
    2. 去标签；
    3. ``html.unescape`` —— PaddleOCR 输出里 ``&nbsp;``/``&amp;``/``&lt;`` 很常见，
       不还原会在表格里显示成字面的 ``&nbsp;``；
    4. 转义 ``|`` —— 否则一格内容被 GFM 当成列分隔符，整张表列数错位；
    5. 压空白 —— HTML 里的缩进/换行会带进单元格。

    ⚠️ PaddleOCR-VL 有时会把单元格内的换行输出成**字面的反斜杠+n**（不是真换行符），
    直接进 GFM 会在表格里显示成 ``\n``。两字序列里前后都是可见字符，不会被
    ``\\s+`` 规则吃掉，所以必须单独替换。
    """
    text = _BR_RE.sub(" ", inner or "")
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = text.replace("\\n", " ").replace("\\r", " ")
    text = text.replace("|", "\\|")
    return re.sub(r"\s+", " ", text).strip()


def _html_table_to_markdown(table_html: str) -> str:
    """单张 HTML 表格 → GFM 表格；无法解析出行时返回空串（调用方保留原 HTML）。

    colspan / rowspan 只做「尽力而为」：colspan 复制成多个同内容单元（保住列数），
    rowspan 不向下填充（GFM 没有合并单元格概念，填充反而会造出虚假数据）。
    法律文书里的表格多是一对一对照表，这种程度足够用，过度设计收益极低。
    """
    rows: list[list[str]] = []
    for row_html in _TR_RE.findall(table_html):
        cells: list[str] = []
        for match in _CELL_RE.finditer(row_html):
            text = _cell_text(match.group(3))
            colspan = _span_value(_COLSPAN_RE, match.group(2))
            cells.append(text)
            # colspan 补空位：只补「列数」不复制文本，避免同一内容重复出现被当成多行数据
            cells.extend([""] * (colspan - 1))
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    # 行列不齐时补空列：GFM 要求每行单元格数一致，否则渲染器会截断或错位
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header, *body = normalized
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + " --- |" * width,
        *("| " + " | ".join(row) + " |" for row in body),
    ]
    return "\n".join(lines)


def _replace_html_table(match: re.Match[str]) -> str:
    """``re.sub`` 回调：转成功就换成 GFM，失败就原样返回整段 HTML。

    原样保留是硬要求——宁可下游看到 raw HTML，也不能因为解析失败把合同条款丢掉。

    转换结果两侧要各自独占一行：PaddleOCR-VL 的 text 里表格常直接贴着前后文字
    （``前文<table>…</table>后文``），不补换行会拼接成
    ``前文| a |`` / ``| --- |后文``，GFM 渲染器会把「后文」当成表格单元格内容。
    """
    original = match.group(0)
    try:
        converted = _html_table_to_markdown(match.group(1))
    except Exception as exc:  # 任何异常都不能导致正文丢失
        logger.warning("HTML 表格转 GFM 失败，保留原始 HTML: %s", exc)
        return original
    if not converted:
        return original

    # 已有换行的位置不再补，避免多出空行把正文切出一堆空白 raw_text
    return "\n" + converted + "\n"


def _convert_html_tables_to_markdown(markdown_text: str) -> str:
    """把 markdown 正文里所有 ``<table>`` 转成 GFM 表格（多表逐个替换）。"""
    if not markdown_text or "<table" not in markdown_text.lower():
        return markdown_text
    return _TABLE_RE.sub(_replace_html_table, markdown_text)


def normalize_model_key(raw: str) -> str:
    """任意写法 → 小写配置键；未知值原样（小写）返回。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    if text in _MODEL_API_NAME_MAP:
        return text
    for key, api_name in _MODEL_API_NAME_MAP.items():
        if text == api_name or text.lower() == api_name.lower():
            return key
    return text.lower()


# 模型 → API 端点类型映射（键统一为小写配置键）
_OCR_ENDPOINT_MODELS = {"pp_ocrv5", "pp_ocrv6", "pp_structure_v3"}
_LAYOUT_ENDPOINT_MODELS = {"paddleocr_vl", "paddleocr_vl_1_5", "paddleocr_vl_1_6"}

# 只有 PP-StructureV3 会在 OCR 信封之外**另带**一份结构化表格几何
# （``result.layoutParsingResults[].prunedResult.table_res_list``）。
# PP-OCRv5/v6 是纯文字 OCR，没有这个信封，不能顺手也去解析（会把空表当结果）。
_STRUCTURED_TABLE_MODEL = "pp_structure_v3"

# 要开**整页方向分类**的模型：版面类（VL 系列）+ PP-StructureV3。
#
# 为什么必须开（p52 实测，2026-11-21）：元数据 ``/Rotate=0`` 但内容躺倒的页，不开时
# 只认出 82 字垃圾（「日22602」「中会限 业」），开了之后是 399 字正确正文；单页耗时
# 34.4s，比不开只多一个分类模型的前向。PP-OCRv5/v6 先不开：纯文字场景为省下那一类
# 罕见页而给每一页都加一次分类模型，性价比不划算。
#
# ⚠️ 开了之后**坐标会整体换到「转正帧」**（``prunedResult.width/height`` 变成转正帧
# 尺寸、``doc_preprocessor_res.angle`` 非 0），必须由消费方反变换回原页帧——本模块只把
# angle 透出（``PaddleOCRApiResult.page_orientations`` / ``ParsedTableResult.page_angle``），
# 反变换在 ``apps.pdf_splitting.services.split.page_rotation`` 里做且只做一次。
_DOC_ORIENTATION_MODELS = _LAYOUT_ENDPOINT_MODELS | {_STRUCTURED_TABLE_MODEL}

#: 方向分类可能给出的直角（与 ``pdf_splitting.split.page_rotation.THETAS`` 同一集合）。
_PAGE_ANGLES = (0, 90, 180, 270)

#: ``pred_html`` 里的单元格开标签（``<td`` / ``<th``）。
_TABLE_CELL_TAG_RE = re.compile(r"<t[dh][\s>]", re.IGNORECASE)


@dataclass(frozen=True)
class PaddleOCRApiImage:
    """版面解析产出的一张图片（印章/照片/图表裁剪）。

    key   = markdown 里引用的相对路径（imgs/img_in_seal_box_xxx.jpg）
    url   = 可直接下载的绝对地址（bcebos），可能过期
    data  = 已下载的原始字节；未下载时为 None
    """

    key: str
    url: str
    data: bytes | None = None
    content_type: str = "image/jpeg"


@dataclass(frozen=True)
class ParsedPageOrientation:
    """一页的方向分类结果（``prunedResult.doc_preprocessor_res`` + 帧尺寸）。

    ``angle`` = 服务端把页面**逆时针**转正了多少度（0/90/180/270，脏值一律按 0）；
    ``width``/``height`` = **转正帧**尺寸（90/270 时与原页互换），拿不到时为 0。

    为什么要单独成对象而不是只给一个 angle：反变换回原页帧同时需要「转了多少」与
    「转正后多大」两个量（像素→归一化的分母是后者），缺一个就换不回去。
    """

    angle: int
    width: int
    height: int


@dataclass(frozen=True)
class ParsedTableResult:
    """PP-StructureV3 量到的一张表（``prunedResult.table_res_list[j]``）。

    ``cell_boxes`` 是**裁图像素**坐标 ``(x0, y0, x1, y1)``，与同一 ``prunedResult`` 的
    ``width``/``height``（= ``image_size``）同量纲。换成页面坐标必须同时带上「裁图在
    页面上的位置」（见 ``apps.pdf_splitting.services.split.table_geometry.map_pixel_rect``）。

    ⚠️ 开启方向分类后这一帧是**转正帧**：``page_angle`` 非 0 时 ``cell_boxes`` /
    ``text_boxes`` 与原页差一次旋转，消费方（表格几何 pass）必须先用
    ``page_rotation.derotate_pixel_box`` 换回原页帧再算页面坐标。

    顺序**不是契约**（2026-11-21 实测）：单页裁图样本 p10/p16/p22 碰巧 row-major，
    批量送整页的 p71/p72/p54/p20 就不是。所以下游不按下标取文本（改按几何归属），
    这里也不再用「框数 == ``<td>`` 数」证明同序 —— 只留一条上界：框数多于渲染格数
    说明结果自相矛盾（重复框/串表），整表跳过。
    """

    cell_boxes: tuple[tuple[float, float, float, float], ...]  # 裁图像素 (x0, y0, x1, y1)
    html: str  # pred_html，拿不到为 ""
    image_size: tuple[int, int] | None  # (width, height)，拿不到为 None
    texts: tuple[str, ...]  # table_ocr_pred.rec_texts（行级 OCR，可为空）
    #: 本页被服务端转正的角度（``doc_preprocessor_res.angle``）；0 = 没转。
    #:
    #: 为什么不塞进 ``image_size``：尺寸只能告诉你「转没转」（宽高互换），告诉不了
    #: 「往哪边转」，而 90 与 270 的框在页面上的落点完全不同。
    page_angle: int = 0
    #: ``table_ocr_pred.rec_boxes``，与 ``texts`` **按下标成对**（同一批行级 OCR 的框）。
    #:
    #: 为什么必须带上框：``cell_box_list`` 的顺序不可依赖（批量送检的样本 p71/p72/p54/p20
    #: 都不是 row-major，见 ``facts/BATCH.md`` §3），所以格内文本只能按「文本框中心落在哪个
    #: 格」归并；只有文本没有框时无法归属，下游只能把格内文本留空。
    #:
    #: 缺失时为 ``()``。长度与 ``texts`` 不等时**整批不可用**（下游按 ``text_source=none``
    #: 处理），绝不按下标硬配。
    text_boxes: tuple[tuple[float, float, float, float], ...] = ()


@dataclass(frozen=True)
class PaddleOCRApiResult:
    """PaddleOCR API 识别结果"""

    text: str  # 合并后的文本
    raw_texts: list[str]  # 原始文本列表
    model: str  # 使用的模型名称
    # 版面解析产出的图片清单。默认空列表是为了向后兼容：
    # OCR 端点（PP-OCRv5/PP-StructureV3）根本不出图，调用方无需区分模型即可直接遍历。
    images: list[PaddleOCRApiImage] = field(default_factory=list)
    # 逐页版面结果（``result.layoutParsingResults`` 原样保留）。
    #
    # 为什么不能只留合并后的 ``text``：双引擎比对需要**逐页**的页码与 block 坐标，
    # 而 ``text`` 是把所有页拼成一坨。丢了这个结构，比对就只能拿整段文本猜页码，
    # 猜出来的页码是假的——分歧会指到错误的页，比不报更糟。
    # 默认空列表：OCR 端点没有这个结构，旧调用方也不会因此炸。
    layout_results: list[dict[str, Any]] = field(default_factory=list)
    # PP-StructureV3 量到的表格几何（见 ``parse_table_results``）。
    #
    # 为什么不塞进 ``layout_results``：几何在**另一个信封**（``layoutParsingResults``），
    # 而 ``text`` 仍只来自 ``ocrResults``——两个信封各管一件事，混在一起会让
    # 「正文从哪来」第二次变得模糊。默认空列表：非 PP-StructureV3 模型没有这个结构。
    tables: list[ParsedTableResult] = field(default_factory=list)
    # 逐页的表格几何（外层下标 = 页序，见 ``parse_table_results_by_page``）。
    #
    # 与 ``tables`` 同源、只是多了页码维度：``tables`` 是给「一页一张裁图」的单页路径用的，
    # 批量送子 PDF 时必须知道「哪张表属于哪一页」，扁平的 ``tables`` 表达不了。
    # 两个字段都保留而不是让调用方自己猜：猜错的代价是把 A 页的格子画到 B 页上。
    table_pages: list[list[ParsedTableResult]] = field(default_factory=list)
    # 逐页方向分类结果（外层下标 = 页序，见 ``parse_page_orientations``）。
    #
    # 为什么必须透出：开启方向分类后**所有**坐标都在转正帧，反变换回原页帧要用到
    # 「转了多少度」与「转正后多大」。透出成数据而不是让调用方再解一遍响应，是为了让
    # 「解析响应」这件事只有本模块一处实现。默认空列表：OCR 端点/旧调用方行为不变。
    page_orientations: list[ParsedPageOrientation] = field(default_factory=list)


def _count_html_cells(html_text: str) -> int:
    """``pred_html`` 里的单元格数（``<td``/``<th`` 开标签计数）。"""
    if not html_text:
        return 0
    return len(_TABLE_CELL_TAG_RE.findall(html_text))


def _as_pruned_result(value: Any) -> dict[str, Any] | None:
    """``page.prunedResult`` → dict；JSON 字符串也认（解析失败当「没有」）。

    ``_parse_ocr_response`` 拿到的 ``prunedResult`` 实测就可能是一个 ``str``，
    所以这里两种形状都要接受；解析不出来视为该页没有结构化结果。
    """
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        logger.warning("PaddleOCR 表格解析: prunedResult 不是合法 JSON 串，已跳过该页")
        return None
    return parsed if isinstance(parsed, dict) else None


def _as_image_size(width: Any, height: Any) -> tuple[int, int] | None:
    """``prunedResult.width/height`` → ``(width, height)``；缺失或非法返回 ``None``。

    宁可给 ``None``（调用方据此退回整表框），也不编一个 1000×1000 的假定尺寸：
    ``cell_box_list`` 是**裁图**像素坐标，尺寸错了换算出来的页面坐标整体偏移。
    """
    try:
        width_px = float(width)
        height_px = float(height)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(width_px) or not math.isfinite(height_px) or width_px <= 0 or height_px <= 0:
        return None
    return round(width_px), round(height_px)


def _as_pixel_box(item: Any) -> tuple[float, float, float, float] | None:
    """单个 ``cell_box`` → 合法像素框；形状不对或退化返回 ``None``。"""
    if not isinstance(item, (list, tuple)) or len(item) < 4:
        return None
    try:
        x0, y0, x1, y1 = (float(item[index]) for index in range(4))
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (x0, y0, x1, y1)) or x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def _as_cell_boxes(raw: Any) -> list[tuple[float, float, float, float]]:
    """``cell_box_list`` → 合法像素框（**保持原序**，顺序是「与 <td> 同序」的前提）。"""
    if not isinstance(raw, (list, tuple)):
        return []
    boxes: list[tuple[float, float, float, float]] = []
    for item in raw:
        box = _as_pixel_box(item)
        if box is None:
            continue
        boxes.append(box)
    return boxes


def _as_rec_texts(raw: Any) -> tuple[str, ...]:
    """``table_ocr_pred.rec_texts`` → 文本元组。

    **不去重、不裁剪、不丢空串**：这批文本是行级 OCR，与 ``rec_polys``/``rec_boxes``
    按下标一一对应，去重（``_collect_rec_texts`` 的做法）会破坏对齐；
    下游（格子文本比对）只按序取用。
    """
    if not isinstance(raw, dict):
        return ()
    texts = raw.get("rec_texts")
    if not isinstance(texts, list):
        return ()
    return tuple(text for text in texts if isinstance(text, str))


def _as_text_boxes(raw: Any) -> tuple[tuple[float, float, float, float], ...]:
    """``table_ocr_pred.rec_boxes`` → 行级 OCR 框（保持原序，逐项校验）。

    与 ``_as_rec_texts`` 分开取而不是拼成对：任一侧有脏项时两侧长度就会不等，
    下游的「长度相等才可用」这道闸门会把它挡掉——比在这里悄悄丢掉一格、
    再让文本与框错位一格要安全得多。
    """
    if not isinstance(raw, dict):
        return ()
    boxes = raw.get("rec_boxes")
    if not isinstance(boxes, list):
        return ()
    return tuple(box for box in (_as_pixel_box(item) for item in boxes) if box is not None)


def _parse_table_entry(entry: Any, *, image_size: tuple[int, int] | None) -> ParsedTableResult | None:
    """``table_res_list[j]`` → ``ParsedTableResult``；不可用时返回 ``None`` 并留痕。"""
    if not isinstance(entry, dict):
        logger.warning("PaddleOCR 表格解析: table_res_list 里有非 dict 项（%s），已跳过", type(entry).__name__)
        return None

    raw_boxes = entry.get("cell_box_list")
    boxes = _as_cell_boxes(raw_boxes)
    if not boxes:
        logger.warning(
            "PaddleOCR 表格解析: 没有可用的 cell_box_list（原始类型 %s），该表已跳过", type(raw_boxes).__name__
        )
        return None

    html_value = entry.get("pred_html")
    html_text = html_value if isinstance(html_value, str) else ""
    # 数量闸门：只拦「框比渲染格还多」这一种脏数据，**不再要求严格相等**。
    #
    # 为什么放宽（2026-11-21 真实 job 523fabce 实测）：
    # ① 长表上 ``cell_box_list(39)`` vs ``<td>(47)`` —— 8 个退化框被 ``_as_cell_boxes``
    #    丢掉，真表被整张跳过；
    # ② PP 的 ``pred_html`` 会带 rowspan/colspan（单页样本一次没见过，长表里有），
    #    那时 ``<td>`` 数本来就不等于格位数。
    #
    # 现在“顺序”已经没有任何消费方了：行列由几何聚类推、文本按几何归属，都不再要求
    # “cell_box_list 与 <td> 同序”。所以只需一个上界：框数超过渲染格数，说明这张
    # 表的结果自相矛盾（或 HTML 不是同一张表），丢掉；否则一律交给几何层的
    # 「列数必须等于 MinerU 网格」+「无重复格位」+「不出表块 bbox」三道闸门。
    expected_cells = _count_html_cells(html_text)
    if expected_cells and len(boxes) > expected_cells:
        logger.warning(
            "PaddleOCR 表格解析: cell_box_list(%d) 多于 pred_html 的 <td>(%d)，该表已跳过（结果自相矛盾）",
            len(boxes),
            expected_cells,
        )
        return None
    if expected_cells and len(boxes) != expected_cells:
        logger.info(
            "PaddleOCR 表格解析: cell_box_list(%d) 与 <td>(%d) 不等（跨度/退化框），交由几何层校验",
            len(boxes),
            expected_cells,
        )

    ocr_pred = entry.get("table_ocr_pred")
    return ParsedTableResult(
        cell_boxes=tuple(boxes),
        html=html_text,
        image_size=image_size,
        texts=_as_rec_texts(ocr_pred),
        text_boxes=_as_text_boxes(ocr_pred),
    )


def _parse_pruned_tables(pruned: dict[str, Any]) -> list[ParsedTableResult]:
    """一个 ``prunedResult`` 里的所有表（``table_res_list``），带上本页的转正角度。"""
    entries = pruned.get("table_res_list")
    if not isinstance(entries, list):
        return []
    image_size = _as_image_size(pruned.get("width"), pruned.get("height"))
    page_angle = _page_orientation(pruned).angle
    parsed: list[ParsedTableResult] = []
    for entry in entries:
        table = _parse_table_entry(entry, image_size=image_size)
        if table is None:
            continue
        parsed.append(replace(table, page_angle=page_angle))
    return parsed


def parse_table_results(result: dict[str, Any]) -> list[ParsedTableResult]:
    """从一次 PP-StructureV3 响应里取出**量到的**表格几何。

    ## 为什么必须读 ``layoutParsingResults`` 这个信封

    ``pp_structure_v3`` 走 ``_OCR_ENDPOINT_MODELS`` 分支，``_parse_ocr_response`` 读的是
    ``result["ocrResults"][i]["prunedResult"]``；那里的键只有
    ``rec_texts/rec_scores/rec_polys/rec_boxes`` 等（纯 OCR 子结果），**没有**
    ``table_res_list``。表格几何在同一响应的**另一个信封**：
    ``result["layoutParsingResults"][i]["prunedResult"]``（含 ``width/height/table_res_list``）。
    所以修法不是「给 ``_parse_ocr_response`` 补字段」，而是多读一个信封。

    ## 取值规则

    1. 主路径 ``layoutParsingResults[].prunedResult.table_res_list``；
    2. 兜底 ``result.table_res_list``（PDF 的 JSONL 切片里会出现不带容器的裸片段行，
       与 ``_parse_jsonl_response`` 的容器判定同源）；
    3. ``prunedResult`` 允许是 JSON 字符串，解析失败即当空；
    4. **一律不抛**：形状不对就跳过该条目——一次付费调用的结果不能因为一条脏数据作废。

    数量闸门（已放宽，2026-11-21 实测）：只有「框数**多于** ``<td>`` 数」才整表跳过
    （结果自相矛盾）；少于则照收——退化框被过滤、PP 输出 rowspan/colspan 都会让两侧
    不相等，严格相等会把真表整张跳过。真正的把关在几何层（列数必须等于 MinerU 网格 /
    无重复格位 / 不出表块 bbox）。
    """
    pages = _layout_pages(result)
    if not pages:
        # 没有 layoutParsingResults 包装时，把 result 本身当成一个 prunedResult（JSONL 裸片段）
        return _parse_pruned_tables(result)

    parsed: list[ParsedTableResult] = []
    for page in pages:
        pruned = _as_pruned_result(page.get("prunedResult"))
        if pruned is None:
            continue
        parsed.extend(_parse_pruned_tables(pruned))
    return parsed


def parse_table_results_by_page(result: dict[str, Any]) -> list[list[ParsedTableResult]]:
    """逐页版本的 ``parse_table_results``：外层下标 = 页序，内层 = 该页的各张表。

    ## 为什么批量路径必须按页分组

    传子 PDF 时响应是 **JSONL，一行 = 一页、行序 = 送检页序**（实测 6 页 6 行、22 页 22 行，
    每行 ``layoutParsingResults`` 恰好 1 项），而 ``table_res_list`` 是**每页各自的列表**
    （p16/p20 各 2 张）。扁平的 ``parse_table_results`` 会把「第 1 页的第 2 张」和
    「第 2 页的第 1 张」连成一片，页码对不上 → 格子会画到别的页上。

    没有 ``layoutParsingResults`` 包装的裸片段行按「一页」处理（与 ``parse_table_results``
    的兜底同源）。
    """
    pages = _layout_pages(result)
    if not pages:
        return [_parse_pruned_tables(result)]

    grouped: list[list[ParsedTableResult]] = []
    for page in pages:
        pruned = _as_pruned_result(page.get("prunedResult"))
        grouped.append([] if pruned is None else _parse_pruned_tables(pruned))
    return grouped


def _layout_pages(result: dict[str, Any]) -> list[dict[str, Any]]:
    """``result["layoutParsingResults"]`` → 只看 dict 项（脏项直接滤掉）。"""
    pages = result.get("layoutParsingResults")
    if not isinstance(pages, list):
        return []
    return [page for page in pages if isinstance(page, dict)]


def _as_page_angle(raw: Any) -> int:
    """``doc_preprocessor_res.angle`` → 0/90/180/270；其它一律 0 并留痕。

    与 ``apps.pdf_splitting.services.split.page_rotation.normalize_theta`` 同一规则
    （本模块不能 import 它：那边的包是服务层，反向 import 会绕成环）。
    缺字段不告警：关闭方向分类时这个字段本来就不存在，每页一条告警会淹没真告警。
    """
    if raw is None:
        return 0
    try:
        angle = int(raw) % 360
    except (TypeError, ValueError):
        angle = -1
    if angle not in _PAGE_ANGLES:
        logger.warning("PaddleOCR 方向解析: angle=%r 不是 0/90/180/270，已按 0 处理", raw)
        return 0
    return angle


def _page_orientation(pruned: dict[str, Any]) -> ParsedPageOrientation:
    """一个 ``prunedResult`` 的方向分类结果（角度 + 转正帧尺寸）。"""
    preprocessor = pruned.get("doc_preprocessor_res")
    raw_angle = preprocessor.get("angle") if isinstance(preprocessor, dict) else None
    size = _as_image_size(pruned.get("width"), pruned.get("height"))
    width, height = size if size is not None else (0, 0)
    return ParsedPageOrientation(angle=_as_page_angle(raw_angle), width=width, height=height)


def parse_page_orientations(result: dict[str, Any]) -> list[ParsedPageOrientation]:
    """从一次响应里取出**逐页**方向（外层下标 = 页序）。

    形状与 ``parse_table_results_by_page`` 同源：主路径
    ``layoutParsingResults[].prunedResult.doc_preprocessor_res``，没有容器包装的裸片段行按
    「一页」处理（PDF 的 JSONL 里会出现）。**一律不抛**：脏 angle 归 0，脏尺寸归 0——
    一次付费调用的结果不能因为一个脏字段作废。

    为什么要按页给：多页 PDF 里可能只有某几页躺倒，angle 得逐页对；一个大一的 angle
    会把正常页的框也转歪。
    """
    pages = _layout_pages(result)
    if not pages:
        return [_page_orientation(result)]
    orientations: list[ParsedPageOrientation] = []
    for page in pages:
        pruned = _as_pruned_result(page.get("prunedResult"))
        orientations.append(_page_orientation(pruned if pruned is not None else {}))
    return orientations
