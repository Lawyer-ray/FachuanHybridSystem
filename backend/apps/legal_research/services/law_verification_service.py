"""法规引用核查服务。

承载 legal_research_api ``/law-verification/check`` 端点下沉的业务：
入参校验、插件可用性探测、威科先行凭证解析（归属校验 + 解密）、
HTTP 会话建立与法规引用核查执行。

失败语义沿用 API 时期的约定——ValidationException / NotFoundError /
PermissionDenied / ExternalServiceError（均为 apps.core.exceptions，
经全局异常处理器渲染），成功返回 ``{"references": [...], "total": N}``。
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from apps.core.exceptions import ExternalServiceError, NotFoundError, PermissionDenied, ValidationException

logger = logging.getLogger(__name__)


def sanitize_weike_login_url(raw_url: Any) -> str | None:
    """仅接受 https 的 wkinfo.com.cn（或其子域）登录页，其余回退默认（安全审计 E-13）。"""
    login_url = str(raw_url or "").strip()
    if not login_url:
        return None
    parsed = urlparse(login_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https" and (host == "wkinfo.com.cn" or host.endswith(".wkinfo.com.cn")):
        return login_url
    return None


class LawVerificationService:
    """文档法规引用核查（基于威科先行私有 API）。"""

    def check_references(self, *, text: str, credential_id: int, user: Any) -> dict[str, Any]:
        """核查文档中的法规引用（同步阻塞，含 Playwright/HTTP IO，调用方自行调度线程）。

        Raises:
            ValidationException: text 为空 / 插件未安装（HTTP 400）
            NotFoundError: 凭证不存在（HTTP 404）
            PermissionDenied: 凭证不属于当前律所（HTTP 403）
            ExternalServiceError: 登录失败 / 核查失败（HTTP 502）
        """
        stripped_text = str(text or "").strip()
        if not stripped_text:
            raise ValidationException("text 不能为空", code="TEXT_REQUIRED")

        # 检测插件是否可用（CI 类型检查环境无 plugins 子模块，用 getattr 动态获取
        # 避免 import 语句在有/无 plugins 两环境下互斥的 mypy 报错）
        import plugins as _plugins

        has_law_verification_plugin = getattr(_plugins, "has_law_verification_plugin", None)

        if not callable(has_law_verification_plugin):
            raise ValidationException("法规核查插件未安装", code="PLUGIN_NOT_INSTALLED")

        # 获取威科先行凭证
        from apps.core.security.secret_codec import SecretCodec
        from apps.organization.models import AccountCredential

        try:
            cred = AccountCredential.objects.select_related("lawyer").get(id=credential_id)
        except AccountCredential.DoesNotExist:
            raise NotFoundError(
                message=f"凭证 ID {credential_id} 不存在", code="CREDENTIAL_NOT_FOUND", errors={}
            ) from None

        # 安全审计 A-07：凭证归属校验（superuser 例外），与 LegalResearchTaskService 同口径
        if not getattr(user, "is_superuser", False) and cred.lawyer.law_firm_id != getattr(user, "law_firm_id", None):
            raise PermissionDenied(message="无权限使用该账号凭证", code="CREDENTIAL_FORBIDDEN", errors={})

        codec = SecretCodec()
        password = codec.try_decrypt(cred.password)

        # 建立威科先行会话
        from apps.legal_research.services.sources.weike.client import WeikeCaseClient
        from plugins.weike_api_private.adapter import PrivateWeikeApiAdapter

        adapter = PrivateWeikeApiAdapter()
        client = WeikeCaseClient()

        try:
            session = adapter.open_http_session(
                client=client,
                username=cred.account,
                password=password,
                # 安全审计 E-13：login_url 强制 wkinfo 域白名单 + https，
                # 防止经凭证 url 字段把账号密码提交到任意站点。
                login_url=sanitize_weike_login_url(cred.url),
            )
        except Exception as e:
            raise ExternalServiceError(f"威科先行登录失败: {e}", code="WEIKE_LOGIN_FAILED") from e

        # 定义回调函数
        def search_laws(law_name: str) -> list[dict[str, Any]]:
            # adapter 的返回类型随 plugins 子模块存在与否在 list[dict]/Any 间变化，
            # 显式构造结果让两种环境都通过类型检查
            results: list[dict[str, Any]] = list(adapter.search_laws_via_api(session=session, keyword=law_name))
            return results

        def fetch_article(doc_id: str, article_num: int) -> str | None:
            article: str | None = adapter.fetch_law_article_via_api(
                session=session, doc_id=doc_id, article_num=article_num
            )
            return article

        # 执行核查
        from plugins.weike_api_private.law_verification import verify_references

        try:
            results = verify_references(stripped_text, search_laws_fn=search_laws, fetch_article_fn=fetch_article)
        except Exception as e:
            raise ExternalServiceError(f"核查失败: {e}", code="VERIFY_FAILED") from e

        return {
            "references": [
                {
                    "law_name": r.get("law_name", ""),
                    "article_num": r.get("article_num"),
                    "status": r.get("status"),
                    "validity": r.get("validity"),
                    "article_text": r.get("article_text"),
                    "reference_text": r.get("reference_text"),
                    "similarity": r.get("similarity"),
                    "weike_url": r.get("weike_url"),
                }
                for r in results
            ],
            "total": len(results),
        }
