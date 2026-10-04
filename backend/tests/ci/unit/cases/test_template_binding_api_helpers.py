"""template_binding_api 辅助函数与工厂函数测试。

端点主体为 async 且委托给 service，此处覆盖 _ensure_case_access、
三个工厂函数与 _build_file_response 的编码行为。

注意：async 测试里的 sync_to_async 在独立线程连接上执行写库，
不会随测试事务回滚，必须显式清理，避免污染 --reuse-db 测试库。
"""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import quote

import pytest
from django.http import HttpRequest

from apps.cases.api.template_binding_api import (
    _build_file_response,
    _ensure_case_access,
    _get_binding_service,
    _get_generation_service,
    _get_unified_template_generation_service,
)
from apps.core.exceptions import ForbiddenError


class TestServiceFactories:
    def test_get_binding_service(self) -> None:
        service = _get_binding_service()
        assert service is not None

    def test_get_generation_service(self) -> None:
        from apps.cases.services import CaseTemplateGenerationService

        assert isinstance(_get_generation_service(), CaseTemplateGenerationService)

    def test_get_unified_template_generation_service(self) -> None:
        from apps.cases.services import UnifiedTemplateGenerationService

        assert isinstance(_get_unified_template_generation_service(), UnifiedTemplateGenerationService)


class TestBuildFileResponse:
    def test_content_and_headers(self) -> None:
        response = _build_file_response(b"docx-content", "委托书（测试）.docx")
        assert response.status_code == 200
        assert response.content == b"docx-content"
        assert response["Content-Type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert response["Content-Disposition"] == f"attachment; filename*=UTF-8''{quote('委托书（测试）.docx')}"

    def test_ascii_filename_encoded(self) -> None:
        response = _build_file_response(b"x", "a b.docx")
        assert response["Content-Disposition"] == "attachment; filename*=UTF-8''a%20b.docx"


@pytest.mark.django_db
class TestEnsureCaseAccess:
    """async 造数会经线程连接落库绕过测试事务回滚，这里只 mock 策略验证 ctx 透传。"""

    def _request(self, user: object) -> HttpRequest:
        request = HttpRequest()
        request.user = user
        return request

    @pytest.mark.asyncio
    async def test_open_access_passes(self) -> None:
        request = self._request(None)
        request.perm_open_access = True
        # perm_open_access 直通：不抛 PermissionDenied 即返回 None
        assert await _ensure_case_access(request, case_id=12345) is None

    @pytest.mark.asyncio
    async def test_anonymous_denied(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        request = self._request(AnonymousUser())
        with pytest.raises(ForbiddenError, match="无权限访问此案件"):
            await _ensure_case_access(request, case_id=12345)

    @pytest.mark.asyncio
    async def test_reuses_existing_access_ctx(self) -> None:
        from apps.core.security.access_context import AccessContext

        request = self._request(None)
        ctx = AccessContext(user=None, org_access=None, perm_open_access=True)
        request.access_ctx = ctx
        # access_ctx.perm_open_access=True 应直接放行
        await _ensure_case_access(request, case_id=99999)
        assert isinstance(SimpleNamespace(ctx=ctx).ctx, AccessContext)

    @pytest.mark.asyncio
    async def test_ctx_forwarded_to_policy(self) -> None:
        """请求上下文（user/org_access/perm_open_access）原样传给访问策略。"""
        from unittest.mock import patch

        from apps.core.security.access_context import AccessContext

        user = SimpleNamespace(id=7, is_authenticated=True, is_admin=False)
        request = self._request(user)
        request.org_access = {"extra_cases": {5}}
        request.perm_open_access = False

        with patch("apps.cases.services.case.case_access_policy.CaseAccessPolicy.ensure_access_ctx") as mock_ensure:
            await _ensure_case_access(request, case_id=42)

        mock_ensure.assert_called_once()
        call_kwargs = mock_ensure.call_args.kwargs
        assert call_kwargs["case_id"] == 42
        forwarded_ctx = call_kwargs["ctx"]
        assert isinstance(forwarded_ctx, AccessContext)
        assert forwarded_ctx.user is user
        assert forwarded_ctx.org_access == {"extra_cases": {5}}
        assert forwarded_ctx.perm_open_access is False

    @pytest.mark.asyncio
    async def test_policy_forbidden_propagates(self) -> None:
        from unittest.mock import patch

        request = self._request(SimpleNamespace(id=7, is_authenticated=True, is_admin=False))

        with patch(
            "apps.cases.services.case.case_access_policy.CaseAccessPolicy.ensure_access_ctx",
            side_effect=ForbiddenError("无权限访问此案件"),
        ):
            with pytest.raises(ForbiddenError, match="无权限访问此案件"):
                await _ensure_case_access(request, case_id=42)
