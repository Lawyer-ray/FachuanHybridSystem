"""元典案例检索客户端（REST，只接两个接口）。

- ``rh_ptal_search``（POST）普通案例关键词检索
- ``rh_case_details``（GET）案例详情，``id`` + ``type=ptal``

语义检索 ``case_vector_search`` 明确不做。分页参数是 **camelCase 的
``pageSize`` / ``pageNo``**——``page_size`` / ``page`` / ``offset`` / ``pageNum`` /
``size`` 会被服务端静默忽略（不报错，恒返回默认 10 条第 1 页），所以绝不写错名。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .config import YuandianConfig, YuandianConfigError, key_label, load_yuandian_config
from .transport import YuandianRequestError, YuandianTransport
from .types import YuandianCaseDetail, YuandianSearchItem, YuandianSession

logger = logging.getLogger(__name__)

SEARCH_ROUTE_KEY = "rh_ptal_search"
DETAIL_ROUTE_KEY = "rh_case_details"
DETAIL_TYPE = "ptal"
PAGE_SIZE = 10
DEFAULT_SEARCH_MODE = "and"

#: 实测 ``ah`` 有时是案号、有时其实是**案由**（不过滤 ``wszl`` 时会给出「买卖合同纠纷」）。
#: 只有这个形态才当案号采信，否则 ``document_number`` 必须留空。
DOCUMENT_NUMBER_PATTERN = re.compile(r"（\d{4}）.*号")


class YuandianCaseClient:
    """实现 ``sources/base.py`` 的 ``CaseSourceClient`` 五个方法。"""

    def __init__(
        self,
        *,
        config: YuandianConfig | None = None,
        transport: YuandianTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or YuandianTransport()

    # ── 会话 ────────────────────────────────────────────────
    def open_session(self, *, username: str, password: str, login_url: str | None = None) -> YuandianSession:
        """打开会话。

        元典**没有账号密码概念**：``username`` / ``password`` / ``login_url`` 一律忽略
        （任务凭据里填什么都不影响），key 只从系统配置 ``YUANDIAN_API_KEYS`` 取。
        """
        config = self._resolve_config()
        if not config.api_keys:
            raise YuandianConfigError("元典数据源未配置 API Key：请在系统配置里填 YUANDIAN_API_KEYS（每行一把 key）")
        logger.info(
            "元典会话就绪",
            extra={
                "base_url": config.base_url,
                "key_count": len(config.api_keys),
                "key_labels": [key_label(api_key) for api_key in config.api_keys],
                "concurrency_per_key": config.concurrency_per_key,
            },
        )
        return YuandianSession(
            api_keys=config.api_keys,
            cursor=0,
            base_url=config.base_url,
            concurrency_per_key=config.concurrency_per_key,
            http_client=self._transport.open_client(),
        )

    # ── 检索 ────────────────────────────────────────────────
    def search_cases(
        self,
        *,
        session: YuandianSession,
        keyword: str,
        max_candidates: int,
        max_pages: int = 10,
        offset: int = 0,
        raw_payload: dict[str, Any] | None = None,
    ) -> list[YuandianSearchItem]:
        """关键词检索。

        ``offset`` 是**精确翻页**：``pageNo = offset // pageSize + 1``，页内剩余偏移自己
        切片（executor 用 ``inspect.signature`` 看到有 ``offset`` 就走这一支）。整次调用
        用同一个 ``pageSize``，翻页网格才不会在多页之间错位。
        """
        query = str(keyword or "").strip()
        start = max(0, int(offset))
        if not query or int(max_candidates) <= 0 or int(max_pages) <= 0:
            return []

        page_size = max(1, min(PAGE_SIZE, int(max_candidates)))
        page_no = start // page_size + 1
        intra_page_offset = start % page_size
        filters = _search_filters(raw_payload)

        collected: list[YuandianSearchItem] = []
        pages_fetched = 0
        hit_total: Any = None

        while len(collected) < int(max_candidates) and pages_fetched < int(max_pages):
            body: dict[str, Any] = {
                "qw": query,
                "search_mode": DEFAULT_SEARCH_MODE,
                "pageSize": page_size,
                "pageNo": page_no,
            }
            body.update(filters)
            envelope = self._transport.request_json(
                session=session,
                route_key=SEARCH_ROUTE_KEY,
                method="POST",
                json_body=body,
            )
            data = envelope.get("data")
            data = data if isinstance(data, dict) else {}
            hit_total = data.get("total", hit_total)
            rows = _search_rows(data)
            pages_fetched += 1
            if not rows:
                break

            is_last_page = len(rows) < page_size
            if intra_page_offset:
                rows = rows[intra_page_offset:]
                intra_page_offset = 0
            for row in rows:
                item = _build_search_item(row)
                if item is None:
                    continue
                collected.append(item)
                if len(collected) >= int(max_candidates):
                    break
            if is_last_page:
                break
            page_no += 1

        logger.info(
            "元典检索完成",
            extra={
                "task_id": session.task_id,
                "keyword": query,
                "offset": start,
                "page_size": page_size,
                "pages_fetched": pages_fetched,
                "returned": len(collected),
                "hit_total": hit_total,
            },
        )
        return collected

    # ── 详情 ────────────────────────────────────────────────
    def fetch_case_detail(self, *, session: YuandianSession, item: YuandianSearchItem) -> YuandianCaseDetail:
        """取案例详情。``content`` 是**全文**（检索响应里的那个只是片段）。"""
        doc_id = str(item.doc_id_unquoted or item.doc_id_raw).strip()
        if not doc_id:
            raise YuandianRequestError("元典案例详情缺少 id")
        envelope = self._transport.request_json(
            session=session,
            route_key=DETAIL_ROUTE_KEY,
            method="GET",
            params={"id": doc_id, "type": DETAIL_TYPE},
        )
        data = envelope.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise YuandianRequestError(f"元典案例详情为空: id={doc_id}")
        return _build_case_detail(data[0], item=item)

    # ── 附件 ────────────────────────────────────────────────
    def download_pdf(self, *, session: YuandianSession, detail: YuandianCaseDetail) -> tuple[bytes, str] | None:
        """元典没有 PDF 接口：恒返回 ``None``，**不发任何请求**。

        已知浪费：``executor_components/source_gateway.py`` 的 ``_download_pdf_with_retry``
        会把 ``None`` 当「暂时拿不到」重试 ``DOWNLOAD_RETRY_ATTEMPTS`` 次。这里每次调用都是
        纯本地返回，只空转不产生流量与费用；该文件的改动属另一条 lane，本适配器不越界。
        """
        return None

    # ── URL 导入（威科专属，不在 base Protocol 上）────────────
    def search_cases_from_url(
        self,
        *,
        session: YuandianSession,
        url: str,
        max_candidates: int,
    ) -> tuple[list[YuandianSearchItem], None]:
        """元典不支持 URL 导入。

        恒返回 ``([], None)``：``executor.py`` 里 ``intercepted_payload`` 为假就会回落到
        常规关键词检索，因此**不需要改 executor**。
        """
        logger.warning(
            "元典不支持 URL 导入，已回落到常规关键词检索",
            extra={
                "task_id": session.task_id,
                "url_length": len(str(url or "")),
                "max_candidates": max_candidates,
            },
        )
        return [], None

    def _resolve_config(self) -> YuandianConfig:
        if self._config is not None:
            return self._config
        return load_yuandian_config()


# ── 模块级纯函数 ────────────────────────────────────────────
def _search_filters(raw_payload: dict[str, Any] | None) -> dict[str, list[str]]:
    """只透传元典认得的两个过滤器；``raw_payload`` 里其它键（威科专属）一律丢弃。"""
    if not raw_payload:
        return {}
    filters: dict[str, list[str]] = {}
    for field in ("wszl", "ay"):
        values = _filter_values(raw_payload.get(field))
        if values:
            filters[field] = values
    return filters


def _filter_values(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set, frozenset)):
        return [text for text in (str(item or "").strip() for item in value) if text]
    return []


def _search_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("lst")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _build_search_item(row: dict[str, Any]) -> YuandianSearchItem | None:
    doc_id = _text(row.get("id"))
    if not doc_id:
        return None
    return YuandianSearchItem(
        doc_id_raw=doc_id,
        doc_id_unquoted=doc_id,
        detail_url=_text(row.get("url")),
        title_hint=_text(row.get("title")),
        search_id="",
        module=_text(row.get("wszl")),
    )


def _build_case_detail(row: dict[str, Any], *, item: YuandianSearchItem) -> YuandianCaseDetail:
    doc_id = _text(row.get("id")) or item.doc_id_unquoted or item.doc_id_raw
    return YuandianCaseDetail(
        doc_id_raw=doc_id,
        doc_id_unquoted=doc_id,
        detail_url=_text(row.get("url")) or item.detail_url,
        search_id="",
        module=_text(row.get("wszl")),
        title=_text(row.get("title")),
        court_text=_text(row.get("jbdw")),
        document_number=_document_number(row.get("ah")),
        judgment_date=_text(row.get("cprq")),
        case_digest=_text(row.get("pjjg")) or _text(row.get("fxgc")),
        content_text=_text(row.get("content")),
        raw_meta=dict(row),
    )


def _document_number(value: Any) -> str:
    """``ah`` 只在形态确为案号时采信（实测有时是案由）。"""
    text = _text(value)
    return text if DOCUMENT_NUMBER_PATTERN.fullmatch(text) else ""


def _text(value: Any) -> str:
    """元典字段有时是字符串、有时是字符串数组（``ay`` 实测恒为数组），统一取首个非空字符串。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        for entry in value:
            if isinstance(entry, str) and entry.strip():
                return entry.strip()
    return ""
