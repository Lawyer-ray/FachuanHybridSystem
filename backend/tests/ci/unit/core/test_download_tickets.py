"""下载票据单元测试（安全审计 2026Q4 M-2）。

覆盖签发票据的完整契约：签名有效性、过期、单次使用（重放被拒）、
URL 拼装/剥离，以及「JWT 不得再走 query」这条红线在 auth 层的落地。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.core import signing
from django.utils import timezone

from apps.core.security.download_tickets import (
    TICKET_SALT,
    TicketError,
    append_ticket,
    consume_download_ticket,
    issue_download_ticket,
    strip_ticket,
)
from apps.organization.models import LawFirm, Lawyer


def _make_lawyer(username: str) -> Lawyer:
    firm, _ = LawFirm.objects.get_or_create(name=f"律所-{username}")
    return Lawyer.objects.create_user(
        username=username,
        password="testpass123",  # pragma: allowlist secret
        law_firm=firm,
    )


@pytest.mark.django_db
class TestDownloadTicket:
    def test_roundtrip(self) -> None:
        ticket = issue_download_ticket(42)
        assert consume_download_ticket(ticket) == 42

    def test_single_use_rejects_replay(self) -> None:
        """单次使用：第二次兑现同一张票必须被拒（重放防护）。"""
        ticket = issue_download_ticket(7)
        assert consume_download_ticket(ticket) == 7
        with pytest.raises(TicketError, match="already used"):
            consume_download_ticket(ticket)

    def test_two_tickets_for_same_user_both_work(self) -> None:
        """jti 独立于 payload：同用户两张票互不影响。"""
        t1 = issue_download_ticket(3)
        t2 = issue_download_ticket(3)
        assert consume_download_ticket(t1) == 3
        assert consume_download_ticket(t2) == 3

    def test_tampered_payload_rejected(self) -> None:
        """改 user_id 后签名不匹配 → 拒。

        注意：攻击者**没有** SECRET_KEY，所以伪造方式是「用另一把 key 签」
        （signing.dumps 默认读 settings.SECRET_KEY，此处显式换一把）。若用同一把
        key 重签，签名本身有效——那不是伪造，是我们自己签发的票。
        """
        ticket = issue_download_ticket(1)
        payload = signing.loads(ticket, salt=TICKET_SALT)
        payload["uid"] = 999
        forged = signing.dumps(payload, key="attacker-chosen-key", salt=TICKET_SALT, compress=True)
        with pytest.raises(TicketError, match="bad signature"):
            consume_download_ticket(forged)

    def test_tampered_uid_with_valid_signature_is_ours(self) -> None:
        """反向确认：同一把 SECRET_KEY 签出的票是「我们签的」，uid 是什么就是什么。

        这条用例的意义在于说明上一条为什么用另一把 key——签名体系只防伪造，
        不防「我们自己签错内容」。票据内容仅含 uid，没有权限语义，所以签错
        的后果仅限于「用错身份」，不会越权（资源访问控制仍由各端点做）。
        """
        ticket = issue_download_ticket(1)
        payload = signing.loads(ticket, salt=TICKET_SALT)
        payload["uid"] = 999
        re_signed = signing.dumps(payload, salt=TICKET_SALT, compress=True)
        assert consume_download_ticket(re_signed) == 999

    def test_expired_ticket_rejected(self) -> None:
        """超过 TTL 的票即使签名正确也拒。"""
        from django.conf import settings

        ttl = int(getattr(settings, "DOWNLOAD_TICKET_TTL_SECONDS", 60))
        ticket = issue_download_ticket(5)
        # 直接构造一个「很久以前签发」的同结构票，绕过真实等待
        payload = signing.loads(ticket, salt=TICKET_SALT)
        old = signing.dumps(payload, salt=TICKET_SALT, compress=True)
        with pytest.MonkeyPatch.context() as mp:
            # 把 TTL 压到 1s，再伪造时间戳过期
            mp.setattr(settings, "DOWNLOAD_TICKET_TTL_SECONDS", 1, raising=False)
            future = timezone.now() + timedelta(seconds=10)
            with pytest.MonkeyPatch.context() as mp2:
                mp2.setattr(signing.time, "time", lambda: future.timestamp())
                with pytest.raises(TicketError, match="expired"):
                    consume_download_ticket(old)

    def test_empty_ticket_rejected(self) -> None:
        with pytest.raises(TicketError, match="empty"):
            consume_download_ticket("")

    def test_garbage_ticket_rejected(self) -> None:
        with pytest.raises(TicketError):
            consume_download_ticket("not-a-real-ticket")

    def test_append_ticket_preserves_existing_query(self) -> None:
        assert append_ticket("/media/a.pdf", "TK") == "/media/a.pdf?ticket=TK"
        assert append_ticket("/api/v1/x?y=1", "TK") == "/api/v1/x?y=1&ticket=TK"
        # 空票据不拼
        assert append_ticket("/media/a.pdf", "") == "/media/a.pdf"

    def test_strip_ticket_removes_param(self) -> None:
        assert strip_ticket("/media/a.pdf?ticket=TK") == "/media/a.pdf"
        assert strip_ticket("/api/v1/x?y=1&ticket=TK") == "/api/v1/x?y=1"
        assert strip_ticket("/media/a.pdf") == "/media/a.pdf"
        assert strip_ticket("/api/v1/x?ticket=TK&y=1") == "/api/v1/x?y=1"


@pytest.mark.django_db
class TestTicketAuthIntegration:
    """票据在 JWTOrSessionAuth 上的落地，以及「JWT 退出 query」这条红线。

    直接调 ``JWTOrSessionAuth()`` 而不是打 ``/media/``：后者是否注册鉴权视图
    取决于 settings/DEBUG，别的测试用 override_settings 改过之后这里会拿到
    404（路由未注册），测的就不是同一件事了。
    """

    def _request(self, *, method: str, query: dict[str, str], user_authenticated: bool = False) -> Any:
        from apps.core.security.auth import JWTOrSessionAuth

        request = MagicMock()
        request.headers = {}
        request.method = method
        request.GET = query
        request.user.is_authenticated = user_authenticated
        return JWTOrSessionAuth()(request)

    def test_valid_ticket_authenticates(self) -> None:
        user = _make_lawyer("tk_user")
        ticket = issue_download_ticket(user.id, resource="media:materials/a.pdf")
        assert self._request(method="GET", query={"ticket": ticket}) is not None

    def test_jwt_in_query_is_no_longer_accepted(self) -> None:
        """M-2 红线：?token=<JWT> 必须不再被接受。"""
        user = _make_lawyer("tk_jwt_user")
        from ninja_jwt.tokens import RefreshToken

        from apps.core.security.jwt_password_binding import bind_password_claim

        access = str(bind_password_claim(RefreshToken.for_user(user), user).access_token)
        assert self._request(method="GET", query={"token": access}) is None

    def test_expired_ticket_does_not_authenticate(self, settings) -> None:
        ticket = issue_download_ticket(_make_lawyer("tk_expired").id)
        settings.DOWNLOAD_TICKET_TTL_SECONDS = 1

        payload = signing.loads(ticket, salt=TICKET_SALT)
        old = signing.dumps(payload, salt=TICKET_SALT, compress=True)
        future = timezone.now() + timedelta(seconds=10)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(signing.time, "time", lambda: future.timestamp())
            assert self._request(method="GET", query={"ticket": old}) is None

    def test_inactive_user_rejected_via_ticket(self) -> None:
        """停用账号经由票据也不得获得访问权（与 ninja_jwt get_user 同口径）。"""
        user = _make_lawyer("tk_inactive")
        user.is_active = False
        user.save(update_fields=["is_active"])
        ticket = issue_download_ticket(user.id)

        assert self._request(method="GET", query={"ticket": ticket}) is None

    def test_ticket_for_deleted_user_rejected(self) -> None:
        user = _make_lawyer("tk_deleted")
        ticket = issue_download_ticket(user.id)
        user.delete()

        assert self._request(method="GET", query={"ticket": ticket}) is None

    def test_ticket_replay_rejected(self) -> None:
        """同一张票第二次兑现即失效——即便 JWT 路径可用也不放行。"""
        ticket = issue_download_ticket(_make_lawyer("tk_replay").id)
        assert self._request(method="GET", query={"ticket": ticket}) is not None
        assert self._request(method="GET", query={"ticket": ticket}) is None

    def test_post_with_ticket_rejected(self) -> None:
        """非安全方法不收票据：query 参数会随 URL 进访问日志。"""
        ticket = issue_download_ticket(_make_lawyer("tk_post").id)
        assert self._request(method="POST", query={"ticket": ticket}) is None
