import pytest

from apps.core.exceptions import PermissionDenied
from apps.organization.models import Lawyer
from apps.organization.services.auth_service import AuthService


@pytest.mark.django_db
class TestAuthServiceBootstrap:
    def setup_method(self):
        self.service = AuthService()

    def test_first_user_register_denied_without_bootstrap_in_production(self, settings):
        settings.DEBUG = False
        settings.ALLOW_FIRST_USER_SUPERUSER = True
        settings.BOOTSTRAP_ADMIN_TOKEN = "bootstrap-secret"

        with pytest.raises(PermissionDenied) as exc_info:
            self.service.register(
                username="u1",
                password="p1",
                real_name="r1",
                bootstrap_token=None,
            )

        assert exc_info.value.code == "BOOTSTRAP_FORBIDDEN"

    def test_first_user_register_allowed_with_bootstrap_token_in_production(self, settings):
        settings.DEBUG = False
        settings.ALLOW_FIRST_USER_SUPERUSER = True
        settings.BOOTSTRAP_ADMIN_TOKEN = "bootstrap-secret"

        result = self.service.register(
            username="u1",
            password="p1",
            real_name="r1",
            bootstrap_token="bootstrap-secret",
        )

        assert result.user.is_superuser is True
        assert result.user.is_admin is True
        assert result.user.is_active is True

    def test_non_first_user_register_does_not_require_bootstrap(self, settings):
        settings.DEBUG = False
        settings.ALLOW_FIRST_USER_SUPERUSER = True
        settings.BOOTSTRAP_ADMIN_TOKEN = "bootstrap-secret"

        Lawyer.objects.create_user(username="existing", password="p0", real_name="e0", is_active=True)

        result = self.service.register(
            username="u2",
            password="p2",
            real_name="r2",
            bootstrap_token=None,
        )

        assert result.user.is_superuser is False
        assert result.user.is_admin is False
        assert result.user.is_active is False
