import pytest
from django.test import RequestFactory

from apps.core.auth import JWTOrSessionAuth
from apps.core.exceptions import PermissionDenied
from apps.organization.models import Lawyer


@pytest.mark.django_db
class TestJWTOrSessionAuthCSRF:
    def setup_method(self):
        self.factory = RequestFactory()
        self.auth = JWTOrSessionAuth()

    def test_session_get_does_not_require_csrf(self):
        user = Lawyer.objects.create_user(username="u1", password="p1", real_name="r1", is_active=True)
        request = self.factory.get("/api/v1/test")
        request.user = user
        assert self.auth(request) == user

    def test_session_post_requires_csrf(self):
        user = Lawyer.objects.create_user(username="u2", password="p2", real_name="r2", is_active=True)
        request = self.factory.post("/api/v1/test", data={})
        request.user = user
        with pytest.raises(PermissionDenied) as exc_info:
            self.auth(request)
        assert exc_info.value.code == "CSRF_FAILED"
