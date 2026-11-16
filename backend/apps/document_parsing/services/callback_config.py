"""云端解析回调（webhook）的开关与 URL 拼装。

为什么单独一个模块：三个后端（textin / mineru 的创建侧）与回调 API（接收侧）
都要回答同一个问题——「这个平台现在到底走回调还是轮询」，判定口径必须唯一，
否则会出现「创建时带了 callback、接收端点却认为未启用」这类静默失联。

**默认全部关闭**：任何一个必需配置缺失都返回 None，调用方据此回退到既有轮询
（``parse_document`` 原路径），行为与引入回调之前完全一致。
"""

from __future__ import annotations

from django.conf import settings

from apps.document_parsing.services.callback_seed import callback_uid

#: 回调接收端点的路径前缀（挂载在 api_v1 的 /document-parsing 之下）
WEBHOOK_PATH_PREFIX = "/api/v1/document-parsing/webhook"

#: 参与回调的云端平台（与 ParserFactory._BACKEND_REGISTRY 的云平台键一致）
CALLBACK_PROVIDERS: tuple[str, ...] = ("textin", "mineru")


def _setting(name: str) -> str:
    """读 settings 里的字符串配置，缺省（含未定义）返回空串。"""
    return str(getattr(settings, name, "") or "").strip()


def webhook_base_url() -> str:
    """回调基地址（不带尾斜杠）；未配置返回空串。"""
    return _setting("DOCUMENT_PARSE_WEBHOOK_BASE_URL").rstrip("/")


def webhook_url(provider: str) -> str | None:
    """给定平台的回调 URL；该平台未启用回调时返回 None。

    启用条件是「基地址已配置」+「平台专属的验签材料已配置」两者同时成立：
    只配基地址而缺验签材料时，回调端点无法区分真伪调用，宁可继续轮询。
    """
    base = webhook_base_url()
    if not base or provider not in CALLBACK_PROVIDERS:
        return None
    if provider == "mineru" and not _setting("MINERU_CALLBACK_UID"):
        return None
    if provider == "textin" and not _setting("TEXTIN_CALLBACK_SECRET"):
        return None
    return f"{base}{WEBHOOK_PATH_PREFIX}/{provider}"


def is_callback_enabled(provider: str) -> bool:
    """该平台当前是否走回调。"""
    return webhook_url(provider) is not None


def webhook_url_for_record(provider: str, record_id: int) -> str | None:
    """带任务定位信息的回调 URL；该平台未启用回调时返回 None。

    MinerU 的回调**不带**我们的记录 id（只有 uid/seed/checksum/content），所以
    uid 必须随 callback URL 带出去（MinerU 会原样放进 ``X-Callback-Url`` 头），
    回调到达时才能定位到具体记录。Textin 的回调带 job_id，不需要额外参数。
    """
    url = webhook_url(provider)
    if url is None:
        return None
    if provider == "mineru":
        return f"{url}?uid={callback_uid(record_id)}"
    return url


def mineru_callback_uid() -> str:
    """MinerU 回调 checksum 里的 uid（未配置返回空串）。"""
    return _setting("MINERU_CALLBACK_UID")


def textin_callback_secret() -> str:
    """Textin 回调签名密钥（未配置返回空串）。"""
    return _setting("TEXTIN_CALLBACK_SECRET")
