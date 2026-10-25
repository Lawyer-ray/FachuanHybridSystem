"""OnlyOffice 编辑器配置端点。

**为什么配置必须后端签发**：DS 开启 JWT 后，config 整体要签名；把
JWT_SECRET 放浏览器等于公开密钥。前端只拿到「已签名的 config」。

**文件如何给 DS 取**：DS 在独立容器/网络里，取不到带 Authorization 头的
请求，且会重试（首拉超时、缓存逐出、forcesave 重组），一次性票据首拉
即失效。因此走 `/onlyoffice/file?src=&sig=` 代理 + 可重复使用的 HMAC
令牌（见 signing.sign_file_token），DS 在 TTL 内可反复回源取同一文件。

**保存如何回来**：DS 在 status=2/6 时回调带 `url`（编辑后文档），由
callback 端点验签 → 下载 → 经 contract_review service 落回任务产物，
并轮换 document key（详见 services/callback_service.py）。
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router, Schema

from apps.core.security.auth import JWTOrSessionAuth

from ..config import aget_config, get_config
from ..services.callback_service import (
    get_or_refresh_session,
    handle_save_callback,
    load_session_by_key,
    note_unknown_key,
    record_callback_status,
)
from ..services.file_proxy import fetch_internal_file, parse_contract_review_path, resolve_user
from ..services.signing import (
    build_editor_config,
    decode_callback_token,
    document_type_of,
    make_document_key,
    sign_file_token,
    verify_file_token,
)

logger = logging.getLogger(__name__)

router = Router(tags=["OnlyOffice"], auth=JWTOrSessionAuth())


class EditorConfigOut(Schema):
    """前端直接交给 DocsAPI.DocEditor 的载荷。"""

    enabled: bool
    docserver_url: str = ""
    config: dict[str, Any] | None = None
    reason: str = ""


@router.get(
    "/editor-config",
    response=EditorConfigOut,
    summary="取 OnlyOffice 编辑器配置（含签名 token）",
)
async def get_editor_config(  # pragma: no cover
    request: HttpRequest,
    file_url: str,
    file_name: str,
    mode: str = "review",
    version: str = "",
) -> Any:
    """按文件生成编辑器配置。

    - `file_url`：站内下载路径。当前仅 `/api/v1/contract-review/{id}/download*`
      享受完整链路（DS 取文件代理 + 保存回写）；其它路径也能取到 config，
      但 DS 回源取文件会被代理拒绝（与 `/file` 白名单一致）。
    - `mode`：`view`（纯只读）/ `review`（锁定修订）/ `edit`（完全编辑）。
    - `version`：内容版本标识（如 updated_at），变了就换 DS 缓存 key。
    """
    cfg = await aget_config()
    if not cfg.enabled:
        return EditorConfigOut(
            enabled=False,
            reason="OnlyOffice 未配置（需 ONLYOFFICE_DOCSERVER_URL / ONLYOFFICE_INTERNAL_URL / ONLYOFFICE_JWT_SECRET）",
        )
    if not document_type_of(file_name):
        return EditorConfigOut(enabled=False, reason="该格式暂不支持在线预览")

    user = getattr(request, "auth", None)
    user_id = str(getattr(user, "pk", "") or "")
    user_name = str(getattr(user, "name", "") or getattr(user, "username", "") or "")

    # document key 只用「原始路径 + version + saved_version」做哈希——
    # 签名参数含时间戳，混进 key 就是每次签发 key 必变（缓存失效 + 协同断裂）。
    document_key = make_document_key(file_url, version, 0)
    parsed = parse_contract_review_path(file_url)
    if parsed is not None:
        _, document_key = await sync_to_async(get_or_refresh_session)(
            task_id=parsed[0], user=user, source_path=file_url, version=version
        )

    token = sign_file_token(cfg.jwt_secret, file_url, user_id)
    signed_path = "/api/v1/onlyoffice/file?src=" + quote(file_url, safe="") + "&sig=" + token

    config = build_editor_config(
        cfg,
        file_url_path=signed_path,
        file_name=file_name,
        document_key=document_key,
        mode=mode,
        user_id=user_id,
        user_name=user_name,
    )
    return EditorConfigOut(enabled=True, docserver_url=cfg.docserver_url, config=config)


@router.post("/callback", auth=None, summary="OnlyOffice 文档状态回调（DS 调用）")
async def document_callback(request: HttpRequest) -> dict[str, int]:
    """DS 状态回调：status=2/6 时下载编辑产物落盘（保存回写），其余记日志。

    验签策略（写路径安全底线）：
    - token 存在但校验失败 → 直接 {"error": 1}，不回落未签名 body；
    - status=2/6（会产生落盘写操作）**必须**持有效签名，否则拒绝；
    - 其余状态无签名也放行（老版本 DS / 未开 inbound JWT 时仅丢日志）。
    """
    import json as _json

    cfg = await aget_config()
    try:
        body: dict[str, Any] = _json.loads(request.body or b"{}")
    except Exception:
        body = {}

    token = str(body.get("token") or "")
    bearer = request.headers.get("Authorization", "")
    if not token and bearer.startswith("Bearer "):
        token = bearer[7:].strip()

    verified: dict[str, Any] | None = None
    if token and cfg.enabled:
        verified = decode_callback_token(cfg, token)
        if verified is None:
            logger.warning("OnlyOffice 回调验签失败，拒绝处理")
            return {"error": 1}
    elif not token:
        logger.warning("OnlyOffice 回调未携带 token（DS 未开 inbound JWT？）")

    payload = verified if verified is not None else body
    inner = payload.get("payload", payload) if isinstance(payload, dict) else {}
    if not isinstance(inner, dict):
        inner = {}
    status = int(inner.get("status", body.get("status", 0)) or 0)
    key = str(inner.get("key", body.get("key", "")) or "")

    if status in (2, 6):
        url = str(inner.get("url", "") or "")
        if verified is None:
            logger.warning("保存回调缺少有效签名，拒绝落盘: key=%s", key)
            return {"error": 1}
        if not url:
            logger.warning("保存回调缺少 url（DS 契约异常）: key=%s", key)
            return {"error": 1}
        session = await sync_to_async(load_session_by_key)(key)
        if session is None:
            await sync_to_async(note_unknown_key)(key)
            return {"error": 1}
        ok = await sync_to_async(handle_save_callback)(session, url, status)
        return {"error": 0 if ok else 1}

    if key:
        session = await sync_to_async(load_session_by_key)(key)
        if session is not None:
            await sync_to_async(record_callback_status)(session, status)
    logger.info("OnlyOffice 回调：key=%s status=%s verified=%s", key, status, verified is not None)
    return {"error": 0}


@router.get("/file", auth=None, summary="DS 取文件代理（签名鉴权，可重复访问）")
def serve_file(request: HttpRequest, src: str, sig: str) -> Any:
    """DS 拉取源文件。

    DS 在独立容器里、无法携带 Authorization 头，且会重试，所以走本端点的
    `?src=&sig=` 签名鉴权（见 signing.sign_file_token），而不是一次性下载票据。

    `src` 只允许站内相对路径（必须以 `/api/` 开头且不含 `://`）——否则就成了
    任意 URL 的开放代理。注意 Django 解析查询串时**已经解码过一次**，这里
    不得再 unquote：签名与验签必须作用于同一字符串，否则含 % 编码的路径
    会出现「签名对象错位 → 稳定 403」。
    """
    from django.http import HttpResponseForbidden, HttpResponseNotFound

    cfg = get_config()
    if not cfg.enabled:
        return HttpResponseForbidden("OnlyOffice 未启用")

    if not src.startswith("/api/") or "://" in src:
        return HttpResponseForbidden("非法的文件路径")

    uid = verify_file_token(cfg.jwt_secret, src, sig)
    if uid is None:
        return HttpResponseForbidden("签名无效或已过期")

    # 按签名里的用户身份去原端点取文件（原端点的权限检查照常生效）
    user = resolve_user(uid)
    if user is None:
        return HttpResponseForbidden("用户不存在")

    resp = fetch_internal_file(src, user)
    if resp is None:
        # 不支持/无权/业务失败（任务未完成、产物缺失等）：对 DS 表现为取不到
        # 文件，回 404 比 500 准确——500 会让 DS 一直重试并污染错误监控
        return HttpResponseNotFound("文件读取失败")
    return resp
