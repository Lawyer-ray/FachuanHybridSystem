"""
PaddleOCR API 云端引擎

调用百度 AI 开放平台的 PaddleOCR API，支持：
- PP-OCRv5：纯文字 OCR，适合证件/快递单号/简单文字提取
- PP-StructureV3：文档结构化分析，适合表格/版面分析
- PaddleOCR-VL：版面分析 + OCR（输出 Markdown），适合复杂文档/合同
- PaddleOCR-VL-1.5：VL 升级版，更高精度版面分析，适合法律文书/密集排版文档

API_URL / Token 通过 SystemConfig 管理。
"""

from __future__ import annotations

import base64
import html
import json
import logging
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

import httpx

from apps.core.services.system_config_service import SystemConfigService
from apps.document_parsing.services.credential_pool import failure_reason_of_active_exception, get_credential_pool

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

# 全部模型统一走 v2 异步 Job API 的单一端点。
#
# 历史包袱：早期是「每模型一个 URL」的同步端点（PADDLEOCR_OCR_API_URL /
# PADDLEOCR_VL_API_URL / PADDLEOCR_VL15_API_URL），那些 aistudio 体验域名已全部
# 失效（返回 500）。v2 Job API 用同一个 URL + `model` 参数区分产品线。
_UNIFIED_JOB_API_URL_KEY = "PADDLEOCR_JOB_API_URL"

# 兼容保留：旧配置键仍在库中时不再被读取（迁移 0012 已删除，此处仅防御性兜底）
_MODEL_URL_KEY_MAP: dict[str, str] = dict.fromkeys(_MODEL_API_NAME_MAP, _UNIFIED_JOB_API_URL_KEY)

# 文件类型：0=PDF, 1=图片
_FILE_TYPE_PDF = 0
_FILE_TYPE_IMAGE = 1

# ── 轮询总超时预算 ────────────────────────────────────────────
#
# 历史值 120s 是纯经验拍出来的，实测单页 PaddleOCR-VL-1.6 就要 ~29s，
# 多页 PDF（整份文件上传，服务端逐页跑）必然超过 120s → 每次都走到「Job 超时」，
# 识别成果白等。所以下限抬到 300s：单页也留足 10 倍余量，抵住服务端排队抖动。
_JOB_TIMEOUT_FLOOR_SECONDS = 300.0
# 每页按「单页实测 × 安全系数」计预算。50s 足够覆盖实测的 29s
# （版面分析 + OCR + 表格识别都在里面），又不至于让一份 100 页的 PDF 把
# 上游 web 请求吊死到几小时。
_JOB_TIMEOUT_PER_PAGE_SECONDS = 50.0

# 轮询间隔（秒）。服务端单页要几十秒，3s 间隔既能较快感知 done，
# 也不会把 Job 查询打成刷接口。
_POLL_INTERVAL_SECONDS = 3.0

# 连接级重试次数。
#
# ⚠️ 语义必须说清楚：``httpx.HTTPTransport(retries=N)`` **只对「连接建立失败」生效**
# （DNS 解析失败、TCP 建连被拒/超时），它不会重发已经送出去的请求。
# 提交任务这类非幂等 POST 因此不会被重复提交——这正是我们想要的；
# 而「请求发出去了但服务端 5xx / 连接中途断开」由下面的轮询容忍逻辑处理。
_HTTP_CONNECT_RETRIES = 2

# 分级超时（秒）。
#
# 为什么要分级而不是给一个总数：
# - connect 短：连不上就是连不上，快速失败让上层尽早重试/告警，不必干等；
# - read/write 长：上传整份 PDF（几 MB~几十 MB）与下载结果 JSON 都可能很慢，
#   给短了会在慢网络下平白失败；
# - pool 短：连接池排队说明并发打满了，等太久只是把请求堆在内存里。
_HTTP_CONNECT_TIMEOUT_SECONDS = 10.0
_HTTP_POOL_TIMEOUT_SECONDS = 10.0

# 轮询（GET 状态 / 下载结果）的读超时：单次读操作的上限，与「Job 总时长」无关。
_HTTP_POLL_READ_TIMEOUT_SECONDS = 60.0
# 提交（POST multipart 上传整份文件）的读写超时，上传慢于轮询是常态。
# 文件越大传得越久，但生命周期总上限由调用方传入的 job_timeout 兜底。
_HTTP_SUBMIT_READ_TIMEOUT_SECONDS = 120.0

# 轮询时允许的「连续失败」次数（5xx / 429 / 网络抖动）。
#
# 为什么要容忍：Job 已经在服务端跑着，一次 502 或一次 keep-alive 连接被对端
# 掐断，并不代表任务失败；立刻抛错等于把已经烧掉的算力白白丢掉。
# 但也不能无限容忍——连续失败往往意味着端点真的挂了，所以超阈值才抛，
# 并且必须是「连续」而非「累计」，偶发抖动不会把额度耗光。
_MAX_CONSECUTIVE_POLL_FAILURES = 5


def persist_images(
    images: list[PaddleOCRApiImage],
    *,
    storage: Any,
    prefix: str,
) -> dict[str, str]:
    """把已下载的图片写入任意 storage（Django ``default_storage`` 或同接口对象）。

    为什么接收 ``storage`` 而不是直接 ``from django.core.files.storage import
    default_storage``：OCR 引擎是纯传输层，被 Celery 任务、管理命令、单测直接调用。
    在模块级硬绑 Django storage 会让它无法在非 Django 上下文裸跑（也拉不进单测）。
    所以落盘能力做成「调用方注入 storage」：Django 侧传 ``default_storage``，
    脚本侧传本地实现，测试侧传内存实现。

    文件命名：以图片自身的 key（``imgs/img_in_seal_box_762_886.jpg``）为基准，
    丢弃目录部分后拼到 ``prefix`` 下。这样「正文里引的是哪个 key」与「存的是哪个
    文件」可以靠文件名对上，方便把 Markdown 里的死链改写成真实地址。

    Args:
        images: 已下载图片（``data`` 为 None 的会被跳过）
        storage: 需提供 ``save(name, content) -> str``
        prefix: 存储前缀目录，如 ``pdf_splitting/ocr_images/{hash}/p031``

    Returns:
        ``{图片 key: 已保存的相对路径}``；未存盘的 key 不出现在结果里。
    """
    if not images or not prefix:
        return {}

    from pathlib import PurePosixPath

    # 延迟 import：ContentFile 只在「真的落盘」时才需要，而本模块被大量单测/脚本
    # 直接 import。把它提到模块顶会让非 Django 上下文也背上这个依赖。
    from django.core.files.base import ContentFile

    saved: dict[str, str] = {}
    for image in images:
        if image.data is None:
            continue
        # key 可能是 ``imgs/xxx.jpg``，只取文件名；不回退到底线字符以外的推导，
        # 因为真实 key 总是带扩展名的扁平文件名。
        filename = PurePosixPath(image.key).name or "image.jpg"
        rel_path = f"{prefix.rstrip('/')}/{filename}"
        try:
            # storage.save 遇到同名会改名（page_0001_x1y2.jpg）。先删旧文件
            # 让重跑同一页时覆盖而不是累积残档——与 ocr_cache 的处理一致。
            if storage.exists(rel_path):
                storage.delete(rel_path)
            saved_path = storage.save(rel_path, ContentFile(image.data))
        except Exception:
            # 单张写盘失败不能让整页识别作废（磁盘满/权限/存储后端抖动）。
            logger.exception("PaddleOCR 图片写盘失败: key=%s", image.key)
            continue
        saved[image.key] = str(saved_path)

    logger.info("PaddleOCR 图片写盘完成: %d/%d -> %s", len(saved), len(images), prefix)
    return saved


def _read_extract_progress(poll_data: dict[str, Any]) -> tuple[int, int | None] | None:
    """从轮询响应里取 ``data.extractProgress``；取不到返回 None。

    服务端未给出 totalPages 时 total 返回 None（下游自己决定展示方式），
    不编造 100% 之类的假进度。脏数据（非 int、负数）一律当未知丢弃。
    """
    payload = poll_data.get("data")
    if not isinstance(payload, dict):
        return None
    progress = payload.get("extractProgress")
    if not isinstance(progress, dict):
        return None

    # 服务端字段可能缺省为 None，直接 int(None) 会抛；先取出来再判定。
    raw_extracted = progress.get("extractedPages")
    if raw_extracted is None:
        return None
    try:
        extracted = int(raw_extracted)
    except (TypeError, ValueError):
        return None
    if extracted < 0:
        return None

    raw_total = progress.get("totalPages")
    total: int | None = None
    if raw_total is not None:
        try:
            total = int(raw_total)
        except (TypeError, ValueError):
            total = None
    if total is not None and total <= 0:
        total = None
    return extracted, total


def _safe_report_progress(
    on_progress: Callable[[int, int | None], None] | None,
    extracted: int,
    total: int | None,
) -> None:
    """调用进度回调，**任何异常都吞掉**。

    回调是旁路观测手段（前端进度条/日志），识别结果才是主目标；
    回调自身写库失败、连接已断等异常绝不允许把识别任务弄挂。
    """
    if on_progress is None:
        return
    try:
        on_progress(extracted, total)
    except Exception as exc:  # 回调异常必须被隔离，不能影响识别
        logger.warning("PaddleOCR 进度回调异常（已忽略）: %s", exc)


def _is_pollable_failure(status_code: int) -> bool:
    """该状态码是否算「可容忍的瞬时失败」。

    5xx 是服务端临时故障，429 是限流——两者都会自愈，值得再等下一轮；
    4xx（鉴权失败、jobId 不存在等）重试一百次也一样，必须立刻失败。
    """
    return status_code >= 500 or status_code == 429


def _default_job_timeout(page_count: int | None = None) -> float:
    """按页数算轮询总超时（秒）。

    公式：``max(基准下限 300s, 页数 × 单页预算 50s)``。
    页数未知（None）时只用基准下限——不能瞎猜，也不为此引入 PDF 解析依赖。

    为什么用 max 而不是「下限 + 页数×预算」：OCR 并行度不确定，页数少时按页
    算出来的值会小于单页实测余量，取 max 保证任何情况都不低于 300s。
    """
    if not page_count or page_count <= 0:
        return _JOB_TIMEOUT_FLOOR_SECONDS
    return max(_JOB_TIMEOUT_FLOOR_SECONDS, float(page_count) * _JOB_TIMEOUT_PER_PAGE_SECONDS)


def _build_http_timeout(read_timeout: float) -> httpx.Timeout:
    """构造分级超时：连接/池短，读/写长（理由见上方常量注释）。"""
    return httpx.Timeout(
        connect=_HTTP_CONNECT_TIMEOUT_SECONDS,
        read=max(read_timeout, _HTTP_POLL_READ_TIMEOUT_SECONDS),
        write=max(read_timeout, _HTTP_POLL_READ_TIMEOUT_SECONDS),
        pool=_HTTP_POOL_TIMEOUT_SECONDS,
    )


def _build_http_transport() -> httpx.HTTPTransport:
    """同步传输层：带连接级重试（只重试建连失败，不重发请求，见常量注释）。"""
    return httpx.HTTPTransport(retries=_HTTP_CONNECT_RETRIES)


def _build_async_http_transport() -> httpx.AsyncHTTPTransport:
    """异步传输层：与同步版同一套连接级重试语义。"""
    return httpx.AsyncHTTPTransport(retries=_HTTP_CONNECT_RETRIES)


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


class PaddleOCRApiEngine:
    """PaddleOCR API 云端引擎"""

    def _looks_like_json_noise(self, text: str) -> bool:
        """判断是否为结构化 JSON/调试噪声文本。"""
        candidate = text.strip()
        if len(candidate) < 10:
            return False

        if (candidate.startswith("{") and candidate.endswith("}")) or (
            candidate.startswith("[") and candidate.endswith("]")
        ):
            return True

        if re.search(r'"[A-Za-z_][\w-]*"\s*:', candidate):
            return True

        json_chars = sum(1 for c in candidate if c in '{}[]":,')
        if len(candidate) >= 30 and (json_chars / len(candidate)) > 0.30:
            return True

        return False

    def __init__(self, model: str | None = None, timeout: float | None = None) -> None:
        """
        初始化 PaddleOCR API 引擎

        Args:
            model: 模型名称，None 时从 SystemConfig 读取
            timeout: 轮询总超时（秒）。None（默认）表示按页数动态计算，
                见 ``_default_job_timeout``：单页/页数未知取基准下限 300s，
                已知页数取 ``max(300s, 页数 × 50s)``。显式传入则一律照用，
                方便测试与特殊场景压住上限。
        """
        self._model = model
        self._timeout = timeout
        self._config_service = SystemConfigService()
        # 凭证池的注册键。生产固定用 "paddleocr"（全部 Worker 共享同一池）；
        # 测试可用 ``_pool_key`` 属性改成唯一值，避免不同用例的失败冷却互相污染。
        self._pool_key = "paddleocr"

    @property
    def model(self) -> str:
        """当前模型的小写配置键（兼容库里的官方名写法）。"""
        raw = self._model or str(self._config_service.get_value("PADDLEOCR_API_MODEL", "pp_ocrv5") or "pp_ocrv5")
        return normalize_model_key(raw)

    @property
    def api_url(self) -> str:
        """获取 API URL（所有模型共用 v2 Job API 端点）"""
        url_key = _MODEL_URL_KEY_MAP.get(self.model, _UNIFIED_JOB_API_URL_KEY)
        return str(self._config_service.get_value(url_key, "") or "")

    @property
    def api_model_name(self) -> str:
        """配置里的模型键 → 服务端认可的官方模型名（发送给 API 的 `model` 字段）。"""
        return _MODEL_API_NAME_MAP.get(self.model, self.model)

    @property
    def api_tokens(self) -> list[str]:
        """解析配置里的全部 token（支持多 Key 并发，每行一个）。

        为什么需要多 token：PaddleOCR 单 Key 有明显的提交排队（实测会返回
        ``10010 任务提交队列已满``），而一份 164 页卷宗按页串行要 80 分钟。
        配置里允许每行填一个 Key，由凭证池轮询分配，既能并发又能绕开单 Key 限流。

        分隔符兼容：换行、逗号、分号都算——用户在 Admin textarea 里习惯不一，
        与其要求「必须换行」，不如都认。空行/空白自动丢弃，避免拿到空 token 去请求。
        """
        raw = str(self._config_service.get_value("PADDLEOCR_API_TOKEN", "") or "")
        return [part.strip() for part in re.split(r"[\r\n,;]+", raw) if part.strip()]

    @property
    def api_token(self) -> str:
        """首个可用 token（向后兼容：单 Key 部署下与旧行为一致）。

        ⚠️ 真实请求**不要**用它——多 Key 场景下必须走凭证池拿绑定 token，
        否则永远打第一个 Key，等于没配多 Key。保留此属性只是为了让
        ``_is_configured`` 与外部旧调用方不炸。
        """
        tokens = self.api_tokens
        return tokens[0] if tokens else ""

    def _credential_pool(self) -> Any:
        """取本引擎对应的凭证池（进程内共享）。

        复用 ``document_parsing`` 的 CredentialPool：它已经做好了轮询分配、
        每 Key 并发上限、按失败原因分档的冷却（瞬时 30s / 鉴权 30min / 额度耗尽到
        下一个配额重置点）与日额度记账。自己再写一份只会多一处语义漂移。

        并发上限固定为 1：PaddleOCR 的任务是「提交 → 轮询 → 下载」长周期，
        同一 Key 上并发多个 Job 更容易撞队列满。1 意味着「一 Key 同时只跑一单」，
        多 Key 才能真正并行。
        """
        tokens = self.api_tokens
        return get_credential_pool(
            provider_key=self._pool_key,
            credentials=tokens,
            concurrency_per_key=1,
        )

    def _is_configured(self) -> bool:
        """检查是否已配置必要的 API 参数"""
        return bool(self.api_url and self.api_tokens)

    def _resolve_job_timeout(self, page_count: int | None) -> float:
        """确定本次 Job 的轮询总超时（秒）。

        只此一处：同步/异步两个入口都调它，避免「同步改了异步忘改」的漂移。
        显式 timeout 优先（全部页数一视同仁），否则按页数动态算。
        """
        if self._timeout is not None:
            return float(self._timeout)
        return _default_job_timeout(page_count)

    def _poll_max_attempts(self, job_timeout: float) -> int:
        """轮询次数上限 = 总超时 / 轮询间隔。

        不用「总超时 / 单次请求超时」是因为 sleep 与请求耗时叠加后刻度难对齐；
        按间隔算出来就是「最多等 job_timeout 秒」这个直观含义。
        """
        return max(1, int(job_timeout / _POLL_INTERVAL_SECONDS))

    def _validate_submit_response(self, response: httpx.Response) -> dict[str, Any]:
        """校验提交响应并返回 jobId 所在的 data 段。同步/异步共用。"""
        if response.status_code != 200:
            logger.warning(
                "PaddleOCR API 提交失败: status=%d, body=%s",
                response.status_code,
                response.text[:500],
            )
            raise RuntimeError(f"PaddleOCR API 返回错误: HTTP {response.status_code}")

        resp_data: dict[str, Any] = response.json()
        if not resp_data.get("data", {}).get("jobId"):
            raise RuntimeError(f"PaddleOCR API 未返回 jobId: {resp_data}")
        return resp_data

    def _validate_result_download(self, response: httpx.Response) -> None:
        """校验结果下载响应。同步/异步共用。

        S43-03（2026-11-23 二轮审计）：原实现下载 jsonUrl 后不看状态码就直接解析。
        httpx 对 4xx/5xx 不抛异常，于是 403（直链过期）/5xx/网关 HTML 错误页会落到
        _parse_job_result：不是被当成「识别成功但一个字都没有」，就是把错误体里的
        字符串字段当成 OCR 正文返回。现在下载失败必须显式抛错。
        """
        if response.status_code != 200:
            raise RuntimeError(f"PaddleOCR API 结果下载失败: HTTP {response.status_code}, body={response.text[:200]}")

    def recognize_bytes(
        self,
        image_bytes: bytes,
        is_pdf: bool = False,
        page_count: int | None = None,
        on_progress: Callable[[int, int | None], None] | None = None,
    ) -> PaddleOCRApiResult:  # pragma: no cover
        """
        识别图片/PDF字节数据中的文字

        使用异步 Job 模式：提交任务 → 轮询状态 → 获取结果。

        Args:
            image_bytes: 图片或 PDF 字节数据
            is_pdf: 是否为 PDF 文件
            page_count: 已知页数，用于按页扩展轮询超时；None 表示未知（只用基准下限）。
                不为了估页数去引入 PDF 解析依赖——调用方知道就传，不知道就不传。
            on_progress: 进度回调 ``on_progress(extracted, total)``。
                extracted 为已处理页数，total 为总页数，服务端未给出时 total 为 None。
                回调抛出的任何异常都会被吞掉（不能因为回调把识别弄挂）。

        Returns:
            PaddleOCRApiResult: 识别结果
        """
        import time

        if not self._is_configured():
            raise RuntimeError("PaddleOCR API 未配置：请先在系统配置中设置 API URL 和 Token")

        model = self.model
        file_type = _FILE_TYPE_PDF if is_pdf else _FILE_TYPE_IMAGE

        # 构建可选参数
        optional_payload: dict[str, Any] = {
            "fileType": file_type,
        }
        if model in _OCR_ENDPOINT_MODELS:
            optional_payload.update(
                {
                    "useDocOrientationClassify": model in _DOC_ORIENTATION_MODELS,
                    "useDocUnwarping": False,
                    "useTextlineOrientation": False,
                }
            )
        elif model in _LAYOUT_ENDPOINT_MODELS:
            optional_payload.update(
                {
                    "useDocOrientationClassify": model in _DOC_ORIENTATION_MODELS,
                    "useDocUnwarping": False,
                    "useChartRecognition": False,
                }
            )

        # 从凭证池拿一个 Key，并在**整个任务周期**（提交 → 轮询 → 下载）绑定使用。
        # 绝不能提交用 A、轮询用 B：Job 归属提交者账号，换 Key 查会 404/无权限。
        pool = self._credential_pool()
        token_idx = pool.acquire()
        if token_idx is None:
            # 全部 Key 都在冷却（连续失败）——宁可明确报错，也不要拿失效 Key 硬打。
            raise RuntimeError("PaddleOCR API 所有凭证均在失败冷却中，请稍后重试")
        headers = {
            "Authorization": f"bearer {pool.credentials[token_idx]}",
        }
        # 任务是否成功：决定归还时是否让该 Key 进冷却。
        token_ok = False
        # 页数用于凭证池的日额度记账：图片固定 1 页，PDF 先看调用方给的页数，
        # 解析出逐页结构后再用实际页数记账（服务端回多少页就记多少页）。
        processed_pages = 1 if not is_pdf else int(page_count or 0)

        # multipart/form-data 上传。
        # `model` 必须发官方模型名（如 PaddleOCR-VL-1.6），不能发配置键（paddleocr_vl_1_6），
        # 否则服务端返回 400「模型传参错误」(code=10007)。
        data = {
            "model": self.api_model_name,
            "optionalPayload": json.dumps(optional_payload),
        }
        files = {
            "file": ("image.jpg", image_bytes, "image/jpeg"),
        }

        # 整份 PDF 一次上传，服务端逐页处理；页数已知就按页扩预算，否则用基准下限。
        job_timeout = self._resolve_job_timeout(page_count if is_pdf else None)
        max_polls = self._poll_max_attempts(job_timeout)

        logger.info(
            "PaddleOCR API 调用: model=%s (api_name=%s), file_type=%s, data_size=%d, job_timeout=%.0fs, max_polls=%d",
            model,
            self.api_model_name,
            file_type,
            len(image_bytes),
            job_timeout,
            max_polls,
        )

        # 连续失败计数：轮询期间的 5xx/429/网络抖动都能容忍，但只忍「连续」几次
        consecutive_failures = 0
        # 状态变化日志的去重标记：轮询可能几十轮，每轮刷一条日志只会淹没真实告警
        last_logged_state: str | None = None

        try:
            # 一个 Client 贯穿「提交 → 轮询 → 下载结果」：
            # 复用同一条 keep-alive 连接，省掉每轮重新 TLS 握手的开销；
            # 更重要的是不把 Client 建在轮询循环里，避免每 3 秒漏掉一批连接池。
            with httpx.Client(
                timeout=_build_http_timeout(_HTTP_SUBMIT_READ_TIMEOUT_SECONDS),
                transport=_build_http_transport(),
                follow_redirects=True,
            ) as client:
                # 提交 Job
                response = client.post(self.api_url, headers=headers, data=data, files=files)
                resp_data = self._validate_submit_response(response)
                job_id = resp_data["data"]["jobId"]

                logger.info("PaddleOCR API Job 已提交: jobId=%s", job_id)

                # 轮询 Job 状态
                for _ in range(max_polls):
                    time.sleep(_POLL_INTERVAL_SECONDS)

                    try:
                        poll_resp = client.get(f"{self.api_url}/{job_id}", headers=headers)
                    except httpx.TransportError as exc:
                        # 网络抖动（读超时、连接被对端关闭）不等于任务失败：
                        # Job 还在服务端跑着，下一轮很可能就恢复了。
                        consecutive_failures += 1
                        logger.warning(
                            "PaddleOCR API 轮询网络异常（连续第 %d/%d 次）: %s",
                            consecutive_failures,
                            _MAX_CONSECUTIVE_POLL_FAILURES,
                            exc,
                        )
                        if consecutive_failures >= _MAX_CONSECUTIVE_POLL_FAILURES:
                            raise RuntimeError(f"PaddleOCR API 轮询连续失败 {consecutive_failures} 次: {exc}") from exc
                        continue

                    if poll_resp.status_code != 200:
                        if not _is_pollable_failure(poll_resp.status_code):
                            # 4xx（鉴权/jobId 不存在）重试无意义，立刻失败暴露问题
                            raise RuntimeError(f"PaddleOCR API 轮询失败: HTTP {poll_resp.status_code}")
                        consecutive_failures += 1
                        logger.warning(
                            "PaddleOCR API 轮询瞬时失败（连续第 %d/%d 次）: HTTP %d",
                            consecutive_failures,
                            _MAX_CONSECUTIVE_POLL_FAILURES,
                            poll_resp.status_code,
                        )
                        if consecutive_failures >= _MAX_CONSECUTIVE_POLL_FAILURES:
                            raise RuntimeError(
                                f"PaddleOCR API 轮询连续失败 {consecutive_failures} 次: HTTP {poll_resp.status_code}"
                            )
                        continue

                    # 走到这里说明服务端正常应答，连续失败计数归零
                    consecutive_failures = 0

                    poll_data = poll_resp.json()
                    payload = poll_data.get("data", {})
                    state = payload.get("state", "") if isinstance(payload, dict) else ""

                    if state != last_logged_state:
                        logger.info("PaddleOCR API Job 状态变化: jobId=%s, state=%s", job_id, state)
                        last_logged_state = state

                    if state == "done":
                        result_url = payload.get("resultUrl", {})
                        jsonl_url = result_url.get("jsonUrl", "") if isinstance(result_url, dict) else ""
                        if not jsonl_url:
                            raise RuntimeError("PaddleOCR API 完成但无 jsonUrl")

                        # 下载结果。jsonUrl 的返回形态**随输入类型不同**（实测）：
                        # - 传图片：单行完整 JSON（`{logId, result:{...}}`）
                        # - 传 PDF：**多行 JSONL**（每行带一部分页）
                        # 所以不能假定单行：_parse_job_result 先试完整 JSON，失败再逐行解。
                        result_resp = client.get(
                            jsonl_url, timeout=_build_http_timeout(_HTTP_POLL_READ_TIMEOUT_SECONDS)
                        )
                        # 下载失败（403/5xx/网关错误页）必须在解析前抛出，否则会被当成空结果。
                        self._validate_result_download(result_resp)
                        # 走到这里才算这个 Key 真的可用；finally 据此决定是否让它进冷却。
                        parsed = self._parse_job_result(result_resp.text, model)
                        token_ok = True
                        if parsed.layout_results:
                            processed_pages = len(parsed.layout_results)
                        return parsed

                    # 进度：done 时已无意义，只在处理中读取，避免把最后一跳重复报给调用方
                    progress = _read_extract_progress(poll_data)
                    if progress is not None:
                        _safe_report_progress(on_progress, *progress)

                    if state == "failed":
                        error_msg = payload.get("errorMsg", "未知错误")
                        raise RuntimeError(f"PaddleOCR API Job 失败: {error_msg}")

            raise RuntimeError(f"PaddleOCR API Job 超时（{job_timeout:.0f}s）")

        except httpx.TimeoutException as e:
            logger.warning("PaddleOCR API 超时: %s", e)
            raise RuntimeError(f"PaddleOCR API 超时: {e}") from e
        except httpx.HTTPError as e:
            logger.warning("PaddleOCR API 网络错误: %s", e)
            raise RuntimeError(f"PaddleOCR API 网络错误: {e}") from e
        finally:
            # 无论成功、失败还是抛异常，都必须归还槽位：
            # 遗忘一次就永久占住一个并发名额，多 Key 池会逐渐“假死”。
            # 失败档位按真实异常判定（401/403→auth，429/额度→quota，其余→transient）；
            # 只有成功时才能确定页数，失败不记账（部分消耗不可知，宁可不记也不双算）。
            pool.release(
                token_idx,
                success=token_ok,
                reason=failure_reason_of_active_exception(),
                pages=processed_pages if token_ok else 0,
            )

    def _parse_job_result(self, raw_text: str, model: str) -> PaddleOCRApiResult:
        """解析 Job API 的结果体。

        v2 Job API 的 jsonUrl 返回形态**随输入类型不同**（实测 2026-11-15，真实 Job API）：

        - **传图片**（单页 jpg）：单行完整 JSON，``{"logId": ..., "result": {...}}``，约 9k 字符；
        - **传 PDF**（多页）：**多行 JSONL**，每行带一部分页（5 页切片回 2 行、约 71k 字符），
          因为一页一条会把几百页的响应挤成几 MB 的单行。

        （``{"logId": ..., "result": {"ocrResults": [...]}}`` 是 OCR 类模型，版面类模型是
        ``result.layoutParsingResults``。）

        所以两者都必须支持：先试完整 JSON，失败再按 JSONL 逐行解析。
        只按单行解会让 PDF 路径的 ``layout_results`` 恒为空，双引擎比对拿不到 VL 数据。
        """
        text = raw_text.strip()
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and isinstance(parsed.get("result"), dict):
                return self._parse_response(parsed, model)
        return self._parse_jsonl_response(raw_text, model)

    def _parse_jsonl_response(self, jsonl_text: str, model: str) -> PaddleOCRApiResult:
        """解析 JSONL 格式的 PaddleOCR API 结果。

        每条 line 可能是 ``{"result": {...}}`` 外层包装，也可能是裸的 result，
        统一取到 ``result`` 再交给 ``_parse_response``，避免两套解析路径漂移。

        ⚠️ PDF 与图片的返回形态**不同**（实测）：
        - 传图片：单行完整 JSON
        - 传 PDF：**多行 JSONL**（每行带一部分页；实测 5 页切片回 2 行，
          行与页不是一一对应）
        所以 ``_parse_job_result`` 不能只按单行解——否则 PDF 路径拿到的
        ``layout_results`` 永远是空的，双引擎比对也就永远没有 VL 数据。
        （这也是为什么下面要**逐行累加**而不是取第一行。）
        """
        all_texts: list[str] = []
        # 逐页版面结构汇聚：多行 JSONL 时每行各自带一部分页面，必须合并而不是只取第一行。
        all_layout_results: list[dict[str, Any]] = []
        all_images: list[PaddleOCRApiImage] = []
        # 表格几何同样要跨行合并：PDF 一片可能切成多行 JSONL，只取某一行就会丢表。
        all_tables: list[ParsedTableResult] = []
        # 逐页的那一份按行序拼接：外层下标就是送检页序，交给调用方按页对齐。
        all_table_pages: list[list[ParsedTableResult]] = []
        # 方向同样逐页累加。**裸片段行不补位**：补了会让页序与 table_pages/layout_results
        # 错位一格，而错位一格就意味着把 A 页的 angle 用到 B 页上。
        all_orientations: list[ParsedPageOrientation] = []
        for line in jsonl_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue

            # 统一收敛到 `result`：有外层就剥掉，没有就当它本身就是 result。
            nested = item.get("result")
            result: dict[str, Any] = nested if isinstance(nested, dict) else item

            # 先看它是否带了预期的容器键（ocrResults / layoutParsingResults）。
            # 裸片段（如单独一行 ``{"rec_texts": [...]}``）没有容器结构，直接交给
            # `_parse_response` 会因找不到容器而返回空文本——历史流式响应里这很常见，
            # 所以这类行改走通用文本提取。
            has_container = isinstance(result.get("ocrResults"), list) or isinstance(
                result.get("layoutParsingResults"), list
            )
            if not has_container:
                # rec_texts 优先按行提取（保持原有顺序语义），否则走通用片段收集。
                rec_texts = self._collect_rec_texts(result)
                all_texts.extend(rec_texts if rec_texts else self._collect_text_fragments(result))
                continue

            try:
                parsed = self._parse_response({"result": result}, model)
            except RuntimeError:
                # 未知 model 类型时退回通用文本提取，不让一行坏数据弄挂整个任务
                all_texts.extend(self._collect_text_fragments(result))
                continue
            all_texts.extend(parsed.raw_texts)
            # 逐页结构与图片同样要合并：下游（双引擎比对）靠它们拿页码与 block 坐标，
            # 只汇总文本会让 PDF 路径的 layout_results 永远为空。
            all_layout_results.extend(parsed.layout_results)
            all_images.extend(parsed.images)
            all_tables.extend(parsed.tables)
            all_table_pages.extend(parsed.table_pages)
            all_orientations.extend(parsed.page_orientations)

        merged = "\n".join(all_texts)
        logger.info(
            "PaddleOCR API (JSONL) 识别完成: model=%s, text_len=%d, layout_pages=%d, images=%d",
            model,
            len(merged),
            len(all_layout_results),
            len(all_images),
        )
        return PaddleOCRApiResult(
            text=merged,
            raw_texts=all_texts,
            model=model,
            images=all_images,
            layout_results=all_layout_results,
            tables=all_tables,
            table_pages=all_table_pages,
            page_orientations=all_orientations,
        )

    def _parse_response(self, data: dict[str, Any], model: str) -> PaddleOCRApiResult:
        """
        解析 API 响应

        PP-OCRv5 / PP-OCRv6 / PP-StructureV3: result.ocrResults[].prunedResult
        PaddleOCR-VL / VL-1.5 / VL-1.6: result.layoutParsingResults[].markdown.text
        """
        result = data.get("result", {})

        if model in _OCR_ENDPOINT_MODELS:
            parsed = self._parse_ocr_response(result, model)
            if model == _STRUCTURED_TABLE_MODEL:
                # PP-StructureV3 要**同时**读两个信封：正文仍只来自 ocrResults（调用方
                # 行为不变），量到的表格几何在 layoutParsingResults（见 parse_table_results）。
                parsed = replace(
                    parsed,
                    tables=parse_table_results(result),
                    table_pages=parse_table_results_by_page(result),
                )
        elif model in _LAYOUT_ENDPOINT_MODELS:
            parsed = self._parse_layout_response(result, model)
        else:
            raise RuntimeError(f"不支持的 PaddleOCR 模型: {model}")

        # 方向逐页透出（单行 JSON 与 JSONL 两条路径共用本方法，所以挂在这里而不是各分支里）。
        orientations = parse_page_orientations(result)
        turned = [item.angle for item in orientations if item.angle]
        if turned:
            logger.info(
                "PaddleOCR 页面方向分类命中: model=%s, pages=%d, angles=%s（坐标在转正帧，需反变换）",
                model,
                len(orientations),
                turned,
            )
        return replace(parsed, page_orientations=orientations)

    def _collect_text_fragments(self, value: Any) -> list[str]:
        """从任意嵌套结构中提取可读文本片段。"""
        fragments: list[str] = []

        if value is None:
            return fragments

        if isinstance(value, str):
            text = value.strip()
            if text and not self._looks_like_json_noise(text):
                fragments.append(text)
            return fragments

        if isinstance(value, list):
            for item in value:
                fragments.extend(self._collect_text_fragments(item))
            return fragments

        if isinstance(value, dict):
            # 常见文本键优先，随后再遍历其余键，避免漏掉嵌套文本
            priority_keys = ("text", "value", "content", "prunedResult", "markdown")
            visited_keys: set[str] = set()

            for key in priority_keys:
                if key in value:
                    visited_keys.add(key)
                    fragments.extend(self._collect_text_fragments(value[key]))

            for key, item in value.items():
                if key in visited_keys:
                    continue
                fragments.extend(self._collect_text_fragments(item))

            return fragments

        text = str(value).strip()
        if text:
            fragments.append(text)

        return fragments

    def _collect_rec_texts(self, value: Any) -> list[str]:
        """仅提取 rec_texts 字段值（支持嵌套与 JSON 字符串）。"""
        texts: list[str] = []

        if value is None:
            return texts

        if isinstance(value, str):
            candidate = value.strip()
            if candidate.startswith("{") or candidate.startswith("["):
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    return texts
                return self._collect_rec_texts(parsed)
            return texts

        if isinstance(value, list):
            for item in value:
                texts.extend(self._collect_rec_texts(item))
            return texts

        if isinstance(value, dict):
            rec_values = value.get("rec_texts")
            if isinstance(rec_values, list):
                for rec in rec_values:
                    if isinstance(rec, str):
                        rec_text = rec.strip()
                        if rec_text:
                            texts.append(rec_text)

            for nested in value.values():
                texts.extend(self._collect_rec_texts(nested))

            if texts:
                # 去重并保持顺序
                deduplicated = list(dict.fromkeys(texts))
                return deduplicated

        return texts

    def _parse_ocr_response(self, result: dict[str, Any], model: str) -> PaddleOCRApiResult:
        """解析 OCR 端点响应（PP-OCRv5 / PP-StructureV3）"""
        ocr_results = result.get("ocrResults", [])
        all_texts: list[str] = []
        rec_texts_hit = 0

        for item in ocr_results:
            pruned = item.get("prunedResult", "")
            rec_texts = self._collect_rec_texts(pruned)
            if rec_texts:
                rec_texts_hit += 1
                all_texts.extend(rec_texts)
                continue

            # 兼容兜底：当 rec_texts 缺失时，退回通用提取
            all_texts.extend(self._collect_text_fragments(pruned))

        merged = "\n".join(all_texts)
        logger.info(
            "PaddleOCR API (OCR) 识别完成: model=%s, text_len=%d, rec_texts_hit=%d/%d",
            model,
            len(merged),
            rec_texts_hit,
            len(ocr_results),
        )
        return PaddleOCRApiResult(text=merged, raw_texts=all_texts, model=model)

    def _parse_layout_response(self, result: dict[str, Any], model: str) -> PaddleOCRApiResult:
        """解析版面分析端点响应（PaddleOCR-VL / VL-1.5 / VL-1.6）。

        只取 ``markdown["text"]``：
        ``markdown`` 里还有 ``images``（相对路径 → bcebos 绝对 URL）。早期实现用
        ``_collect_text_fragments(markdown)`` 递归整个 dict，把图片 URL 当正文收进
        raw_texts（实测污染样如 ``https://pplines-online.bj.bcebos.com/...jpg``），
        下游会把链接当条款正文用。所以此处不走递归，正文只认 text 字符串。

        图片不丢：从 ``markdown["images"]`` 收集成 ``PaddleOCRApiImage``，由调用方
        决定是否下载/落盘（此时 data 为 None）。
        """
        layout_results = result.get("layoutParsingResults", [])
        all_texts: list[str] = []
        images: list[PaddleOCRApiImage] = []

        for item in layout_results:
            markdown_data = item.get("markdown", {})
            if not isinstance(markdown_data, dict):
                continue

            # 正文：只认 markdown["text"]。表中 HTML 表格在 PaddleOCR-VL 输出里很常见，
            # 原样输出会让下游 Markdown 渲染成一坨 raw HTML，所以先转 GFM 再切行。
            markdown_text = markdown_data.get("text")
            if isinstance(markdown_text, str) and markdown_text.strip():
                converted = _convert_html_tables_to_markdown(markdown_text)
                # 切分粒度与 _parse_ocr_response 一致：非空行即一条 raw_text
                all_texts.extend(line.strip() for line in converted.splitlines() if line.strip())

            images.extend(_collect_markdown_images(markdown_data.get("images")))

        merged = "\n".join(all_texts)
        logger.info(
            "PaddleOCR API (Layout) 识别完成: model=%s, text_len=%d, images=%d",
            model,
            len(merged),
            len(images),
        )
        # 逐页结构原样带上：双引擎比对靠它拿页码与 block 坐标（见 layout_results 字段注释）。
        # 只收 dict 项，脏数据直接滤掉——下游按「没有逐页结构」降级，不会拿到半个结果。
        layout_results_out = [item for item in layout_results if isinstance(item, dict)]
        return PaddleOCRApiResult(
            text=merged,
            raw_texts=all_texts,
            model=model,
            images=images,
            layout_results=layout_results_out,
        )

    def extract_text(self, image_bytes: bytes) -> PaddleOCRApiResult:
        """
        提取图片中的文字（兼容 OCRService 接口）

        Args:
            image_bytes: 图片字节数据

        Returns:
            PaddleOCRApiResult: 识别结果
        """
        return self.recognize_bytes(image_bytes, is_pdf=False)

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> PaddleOCRApiResult:
        """
        提取 PDF 中的文字

        Args:
            pdf_bytes: PDF 字节数据

        Returns:
            PaddleOCRApiResult: 识别结果
        """
        return self.recognize_bytes(pdf_bytes, is_pdf=True)

    def download_images(
        self,
        images: list[PaddleOCRApiImage],
        *,
        max_workers: int = 4,
        timeout: float = _HTTP_POLL_READ_TIMEOUT_SECONDS,
    ) -> list[PaddleOCRApiImage]:
        """把版面解析产出的图片（印章/照片/图表裁剪）真实下载下来。

        为什么需要这一步：``markdown["text"]`` 里引用的是 ``imgs/img_in_seal_box_xxx.jpg``
        这种**相对路径**，它在任何地方都不存在——真实地址在 ``markdown["images"]`` 的
        value 里（bcebos 签名 URL）。不下载的话，印章图在 Markdown 里就是一个死链；
        而卷宗里「这枚章盖在哪、是什么章」本身是证据，丢了就找不回来。

        设计取舍：
        - **只下载、不落盘**。本方法是纯传输层，不依赖 Django storage；落盘由调用方
          决定（见 ``persist_images``），这样 OCR 引擎能在 Celery / 脚本 / 测试里裸用。
        - **失败不抛**。单张图 404/超时不应该让整份识别结果作废：该图 ``data`` 保持
          None，调用方按「有 URL 没字节」降级处理（例如只存 URL 留待后补）。
        - **并发下载**。一页可能有十几张印章/照片，串行下载会让识别总耗时翻倍。
        - 签名 URL 会过期，所以下载必须紧跟在识别之后，不能留到第二天补。

        Args:
            images: 待下载的图片（来自 ``PaddleOCRApiResult.images``）
            max_workers: 并发数上限；太高会被对象存储限流
            timeout: 单张图的下载读超时

        Returns:
            与入参同序的新列表；已存在的 ``data`` 不会被覆盖。
        """
        if not images:
            return []

        # 已有字节的（例如上层重试第二次）不必重复下载。
        pending = [img for img in images if img.data is None and img.url]
        if not pending:
            return list(images)

        downloaded: dict[str, bytes] = {}

        def _fetch(image: PaddleOCRApiImage) -> tuple[str, bytes | None]:
            """下载单张图；任何失败都归为 None，由调用方降级处理。"""
            try:
                with httpx.Client(
                    timeout=httpx.Timeout(
                        connect=_HTTP_CONNECT_TIMEOUT_SECONDS,
                        read=timeout,
                        write=timeout,
                        pool=_HTTP_POOL_TIMEOUT_SECONDS,
                    ),
                    transport=httpx.HTTPTransport(retries=_HTTP_CONNECT_RETRIES),
                    follow_redirects=True,
                ) as client:
                    resp = client.get(image.url)
                if resp.status_code != 200:
                    logger.warning(
                        "PaddleOCR 图片下载失败: key=%s status=%d",
                        image.key,
                        resp.status_code,
                    )
                    return image.key, None
                return image.key, resp.content
            except httpx.HTTPError as exc:
                # 超时/连接错都是可容忍的：图丢了不阻断识别结果落地。
                logger.warning("PaddleOCR 图片下载异常: key=%s err=%s", image.key, exc)
                return image.key, None

        # 并发上限取 min(max_workers, 待下载数)：一张图时不必开线程池。
        workers = max(1, min(max_workers, len(pending)))
        if workers == 1:
            for image in pending:
                key, data = _fetch(image)
                if data is not None:
                    downloaded[key] = data
        else:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=workers) as pool:
                for key, data in pool.map(_fetch, pending):
                    if data is not None:
                        downloaded[key] = data

        logger.info(
            "PaddleOCR 图片下载完成: 成功 %d/%d",
            len(downloaded),
            len(pending),
        )
        #
        # 回填字节：同一 key 可能对应多张（同页重复引用），统一按 key 查下载结果。
        # 未下载成功的图保持 data=None，但**保留 url**——上层可存 URL 等后补，
        # 比直接丢掉信息好。
        result: list[PaddleOCRApiImage] = []
        for img in images:
            if img.data is not None:
                result.append(img)
                continue
            payload = downloaded.get(img.key)
            if payload is None:
                result.append(img)
            else:
                result.append(
                    PaddleOCRApiImage(
                        key=img.key,
                        url=img.url,
                        data=payload,
                        content_type=img.content_type,
                    )
                )
        return result

    # ── 异步方法 ──────────────────────────────────────────────

    async def arecognize_bytes(
        self,
        image_bytes: bytes,
        is_pdf: bool = False,
        page_count: int | None = None,
        on_progress: Callable[[int, int | None], None] | None = None,
    ) -> PaddleOCRApiResult:  # pragma: no cover
        """
        异步识别图片/PDF字节数据中的文字

        使用异步 Job 模式：提交任务 → 异步轮询（asyncio.sleep） → 获取结果。
        相比同步版本，轮询等待期间不阻塞事件循环。

        Args:
            image_bytes: 图片或 PDF 字节数据
            is_pdf: 是否为 PDF 文件
            page_count: 已知页数，用于按页扩展轮询超时；None 表示未知（只用基准下限）。
            on_progress: 进度回调 ``on_progress(extracted, total)``，语义与同步版一致：
                total 未知时为 None；回调抛出的任何异常都会被吞掉。

        Returns:
            PaddleOCRApiResult: 识别结果
        """
        import asyncio

        if not self._is_configured():
            raise RuntimeError("PaddleOCR API 未配置：请先在系统配置中设置 API URL 和 Token")

        model = self.model
        file_type = _FILE_TYPE_PDF if is_pdf else _FILE_TYPE_IMAGE

        optional_payload: dict[str, Any] = {"fileType": file_type}
        if model in _OCR_ENDPOINT_MODELS:
            optional_payload.update(
                {
                    "useDocOrientationClassify": model in _DOC_ORIENTATION_MODELS,
                    "useDocUnwarping": False,
                    "useTextlineOrientation": False,
                }
            )
        elif model in _LAYOUT_ENDPOINT_MODELS:
            optional_payload.update(
                {
                    "useDocOrientationClassify": model in _DOC_ORIENTATION_MODELS,
                    "useDocUnwarping": False,
                    "useChartRecognition": False,
                }
            )

        # 与同步版同一套凭证池逻辑：一个 Key 绑定整个任务周期，结束时归还。
        # 注意 acquire 是同步的（池用 threading.Lock），在协程里不可等待，
        # 但它只是几次加锁与数组访问，耗时极短，不会阻塞事件循环。
        pool = self._credential_pool()
        token_idx = pool.acquire()
        if token_idx is None:
            raise RuntimeError("PaddleOCR API 所有凭证均在失败冷却中，请稍后重试")
        headers = {"Authorization": f"bearer {pool.credentials[token_idx]}"}
        token_ok = False
        # 与同步版同口径：图片固定 1 页，PDF 先用调用方给的页数，结果带逐页结构再用实际页数
        processed_pages = 1 if not is_pdf else int(page_count or 0)

        # 同步版同一限制：必须发官方模型名，否则 400「模型传参错误」(code=10007)
        data = {"model": self.api_model_name, "optionalPayload": json.dumps(optional_payload)}
        files = {"file": ("image.jpg", image_bytes, "image/jpeg")}

        # 与同步版共用同一套超时/轮询刻度算法，避免两份逻辑漂移
        job_timeout = self._resolve_job_timeout(page_count if is_pdf else None)
        max_polls = self._poll_max_attempts(job_timeout)

        logger.info(
            "PaddleOCR API 异步调用: model=%s (api_name=%s), file_type=%s, data_size=%d, job_timeout=%.0fs, max_polls=%d",
            model,
            self.api_model_name,
            file_type,
            len(image_bytes),
            job_timeout,
            max_polls,
        )

        # 连续失败计数与状态日志去重，语义同同步版
        consecutive_failures = 0
        last_logged_state: str | None = None

        try:
            # 同一个 AsyncClient 贯穿提交 → 轮询 → 下载。
            # 注意生命周期：必须把整个轮询包在 with 里，不能像历史实现那样
            # 「提交一个 client、轮询另一个 client」——那个写法既浪费连接，
            # 又让提交用的 client 在轮询开始前就被关闭。
            async with httpx.AsyncClient(
                timeout=_build_http_timeout(_HTTP_SUBMIT_READ_TIMEOUT_SECONDS),
                transport=_build_async_http_transport(),
                follow_redirects=True,
            ) as client:
                # 提交 Job
                response = await client.post(self.api_url, headers=headers, data=data, files=files)
                resp_data = self._validate_submit_response(response)
                job_id = resp_data["data"]["jobId"]

                logger.info("PaddleOCR API Job 已提交: jobId=%s", job_id)

                # 异步轮询 — await asyncio.sleep 不阻塞事件循环
                for _ in range(max_polls):
                    await asyncio.sleep(_POLL_INTERVAL_SECONDS)

                    try:
                        poll_resp = await client.get(f"{self.api_url}/{job_id}", headers=headers)
                    except httpx.TransportError as exc:
                        consecutive_failures += 1
                        logger.warning(
                            "PaddleOCR API 异步轮询网络异常（连续第 %d/%d 次）: %s",
                            consecutive_failures,
                            _MAX_CONSECUTIVE_POLL_FAILURES,
                            exc,
                        )
                        if consecutive_failures >= _MAX_CONSECUTIVE_POLL_FAILURES:
                            raise RuntimeError(f"PaddleOCR API 轮询连续失败 {consecutive_failures} 次: {exc}") from exc
                        continue

                    if poll_resp.status_code != 200:
                        if not _is_pollable_failure(poll_resp.status_code):
                            raise RuntimeError(f"PaddleOCR API 轮询失败: HTTP {poll_resp.status_code}")
                        consecutive_failures += 1
                        logger.warning(
                            "PaddleOCR API 异步轮询瞬时失败（连续第 %d/%d 次）: HTTP %d",
                            consecutive_failures,
                            _MAX_CONSECUTIVE_POLL_FAILURES,
                            poll_resp.status_code,
                        )
                        if consecutive_failures >= _MAX_CONSECUTIVE_POLL_FAILURES:
                            raise RuntimeError(
                                f"PaddleOCR API 轮询连续失败 {consecutive_failures} 次: HTTP {poll_resp.status_code}"
                            )
                        continue

                    consecutive_failures = 0

                    poll_data = poll_resp.json()
                    payload = poll_data.get("data", {})
                    state = payload.get("state", "") if isinstance(payload, dict) else ""

                    if state != last_logged_state:
                        logger.info("PaddleOCR API 异步 Job 状态变化: jobId=%s, state=%s", job_id, state)
                        last_logged_state = state

                    if state == "done":
                        result_url = payload.get("resultUrl", {})
                        jsonl_url = result_url.get("jsonUrl", "") if isinstance(result_url, dict) else ""
                        if not jsonl_url:
                            raise RuntimeError("PaddleOCR API 完成但无 jsonUrl")

                        # 下载结果（jsonUrl 可能是 bcebos 直链，不一定带 Authorization）
                        jsonl_resp = await client.get(
                            jsonl_url, timeout=_build_http_timeout(_HTTP_POLL_READ_TIMEOUT_SECONDS)
                        )
                        # S43-03：与同步版一致——下载失败先抛错，不能静默解析成空文本。
                        self._validate_result_download(jsonl_resp)
                        parsed = self._parse_job_result(jsonl_resp.text, model)
                        token_ok = True
                        if parsed.layout_results:
                            processed_pages = len(parsed.layout_results)
                        return parsed

                    progress = _read_extract_progress(poll_data)
                    if progress is not None:
                        _safe_report_progress(on_progress, *progress)

                    if state == "failed":
                        error_msg = payload.get("errorMsg", "未知错误")
                        raise RuntimeError(f"PaddleOCR API Job 失败: {error_msg}")

            raise RuntimeError(f"PaddleOCR API Job 超时（{job_timeout:.0f}s）")

        except httpx.TimeoutException as e:
            logger.warning("PaddleOCR API 超时: %s", e)
            raise RuntimeError(f"PaddleOCR API 超时: {e}") from e
        except httpx.HTTPError as e:
            logger.warning("PaddleOCR API 网络错误: %s", e)
            raise RuntimeError(f"PaddleOCR API 网络错误: {e}") from e
        finally:
            # 与同步版同理：不归还就永久占一个并发名额，多 Key 池会逐渐假死。
            pool.release(
                token_idx,
                success=token_ok,
                reason=failure_reason_of_active_exception(),
                pages=processed_pages if token_ok else 0,
            )

    async def aextract_text(self, image_bytes: bytes) -> PaddleOCRApiResult:
        """异步提取图片中的文字。"""
        return await self.arecognize_bytes(image_bytes, is_pdf=False)

    async def aextract_text_from_pdf(self, pdf_bytes: bytes) -> PaddleOCRApiResult:
        """异步提取 PDF 中的文字。"""
        return await self.arecognize_bytes(pdf_bytes, is_pdf=True)
