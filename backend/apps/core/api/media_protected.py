"""受保护的 media 下载视图（默认关闭，需 MEDIA_REQUIRE_AUTH=true 开启）。

背景：生产环境 ``/media/`` 若由网关/静态服务器直出则无鉴权，证件扫描件、
快递 PDF 等敏感文件可被 URL 枚举读取。本视图提供「可启用的鉴权媒体服务」：

1. 认证：复用 ``JWTOrSessionAuth``（JWT Bearer 头 / ``?token=`` 查询参数 /
   Django Admin Session，见 ``apps/core/security/auth.py``），认证失败返回 403；
2. 路径安全：统一走 ``apps.core.services.storage_service.to_media_abs``，
   resolve 后必须收敛在 ``MEDIA_ROOT`` 内，路径穿越（``../``、绝对路径越界）拒绝；
3. 发送方式（二选一，由 settings 决定）：
   - ``MEDIA_X_ACCEL_PREFIX`` 非空（如 ``/protected_media/``）：只做鉴权，
     返回 ``X-Accel-Redirect`` 响应头，文件由 nginx internal location 发送，
     Django 全程不读文件（性能最佳，适合生产）；
   - 为空：Django ``FileResponse`` 流式返回（通用回退，适合无 nginx 场景）。

启用步骤（运维侧）：

1. 环境变量 ``MEDIA_REQUIRE_AUTH=true``；
2. 网关不再直出 ``/media/``，改为转发到 Django；
3. （可选，推荐）``MEDIA_X_ACCEL_PREFIX=/protected_media/`` 启用 X-Accel 模式。

nginx 配置片段（X-Accel 模式）::

    # 1) /media/ 交给 Django 鉴权（替代原先的静态直出 / alias）
    location /media/ {
        proxy_pass http://django_upstream;   # 按现有网关 upstream 配置调整
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 2) internal location：外部直接访问 404，仅 Django 返回的
    #    X-Accel-Redirect 可内部跳转到此处
    location /protected_media/ {
        internal;
        alias /path/to/backend/media/;        # = MEDIA_ROOT，结尾斜杠必须保留
    }

DEBUG=True 时本视图不接管路由（开发环境仍由 ``django.views.static.serve`` 直出，
见 ``apiSystem/urls.py`` 媒体路由分支）。
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import default_storage
from django.http import (
    FileResponse,
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseForbidden,
    HttpResponseNotFound,
)
from django.views.decorators.http import require_http_methods

from apps.core.exceptions import PermissionDenied, ValidationException
from apps.core.security.auth import JWTOrSessionAuth
from apps.core.services.storage_service import _get_media_root, to_media_abs

logger = logging.getLogger("apps.core.media")

_auth = JWTOrSessionAuth()


def _authenticated(request: HttpRequest) -> bool:
    """JWT（Bearer 头 / ?token=）或 Session 认证，失败返回 False（不抛出）。"""
    try:
        user = _auth(request)
    except PermissionDenied:
        return False
    return bool(user is not None and getattr(user, "is_authenticated", False))


@require_http_methods(["GET", "HEAD"])
def serve_protected_media(request: HttpRequest, path: str) -> HttpResponseBase:
    """受保护的 /media/ 下载视图：先认证（403），再收敛路径（穿越 404），最后发送文件。

    X-Accel 模式下不读文件、不做存在性检查（由 nginx internal location 负责），
    仅返回鉴权结果对应的 ``X-Accel-Redirect`` 头。
    """
    if not _authenticated(request):
        logger.info("media_access_denied", extra={"path_prefix": path.split("/", 1)[0]})
        return HttpResponseForbidden()

    try:
        abs_path = to_media_abs(path)
        media_root_str = _get_media_root()
    except ValidationException:
        # 空路径 / 越界（含 ../ 穿越、绝对路径不在 MEDIA_ROOT 内）一律 404，不泄露路径有效性
        return HttpResponseNotFound()
    if not media_root_str:  # 防御：to_media_abs 已确保非空，此处不可达
        return HttpResponseNotFound()

    media_root = Path(media_root_str).resolve()
    rel_path = abs_path.relative_to(media_root).as_posix()
    content_type = mimetypes.guess_type(abs_path.name)[0] or "application/octet-stream"

    accel_prefix = getattr(settings, "MEDIA_X_ACCEL_PREFIX", "")
    if accel_prefix:
        response = HttpResponse()
        response["X-Accel-Redirect"] = accel_prefix.rstrip("/") + "/" + quote(rel_path)
        response["Content-Type"] = content_type
        return response

    # 流式回读统一走 storage API：相对路径经 Django storage 的 safe_join 收敛，
    # 不以用户输入直接构造文件系统路径
    try:
        return FileResponse(default_storage.open(rel_path), content_type=content_type)
    except (FileNotFoundError, SuspiciousFileOperation, ValueError):
        return HttpResponseNotFound()
