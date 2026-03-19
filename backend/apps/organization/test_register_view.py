from __future__ import annotations

import pytest
from django.core.cache import cache
from django.urls import reverse

from apps.core.models import SystemConfig
from apps.organization.models import Lawyer
from apps.organization.services.auth_service import AUTO_REGISTER_BOOTSTRAP_USED_KEY


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()


@pytest.mark.django_db
def test_register_page_shows_auto_register_button_for_first_visit(client) -> None:
    response = client.get(reverse("admin_register"))
    content = response.content.decode("utf-8")

    assert response.status_code == 200
    assert "自动注册默认超级管理员" in content
    assert 'autocomplete="username"' in content
    assert content.count('autocomplete="new-password"') == 2

    permissions_policy = response.headers["Permissions-Policy"]
    assert "geolocation=()" in permissions_policy
    assert "camera=()" in permissions_policy
    assert "microphone=()" in permissions_policy


@pytest.mark.django_db
def test_auto_register_creates_default_superuser_and_hides_button_afterwards(client) -> None:
    response = client.post(reverse("admin_register"), {"action": "auto_register"}, follow=False)

    assert response.status_code == 302
    assert response.url == reverse("admin:index")

    user = Lawyer.objects.get(username="法穿")
    assert user.real_name == "法穿"
    assert user.is_superuser is True
    assert user.is_staff is True
    assert user.is_admin is True
    assert user.is_active is True

    bootstrap_flag = SystemConfig.objects.get(key=AUTO_REGISTER_BOOTSTRAP_USED_KEY)
    assert bootstrap_flag.value == "true"

    follow_up = client.get(reverse("admin_register"))
    assert follow_up.status_code == 200
    assert "自动注册默认超级管理员" not in follow_up.content.decode("utf-8")


@pytest.mark.django_db
def test_manual_register_marks_bootstrap_as_consumed_even_if_user_deleted(client, settings) -> None:
    settings.ALLOW_FIRST_USER_SUPERUSER = False

    response = client.post(
        reverse("admin_register"),
        {
            "username": "张三",
            "password1": "Strong1234!",  # pragma: allowlist secret
            "password2": "Strong1234!",  # pragma: allowlist secret
        },
        follow=False,
    )

    assert response.status_code == 302
    assert response.url == reverse("admin:login")
    assert Lawyer.objects.filter(username="张三").exists() is True
    assert SystemConfig.objects.filter(key=AUTO_REGISTER_BOOTSTRAP_USED_KEY, value="true").exists() is True

    Lawyer.objects.all().delete()

    follow_up = client.get(reverse("admin_register"))
    assert follow_up.status_code == 200
    assert "自动注册默认超级管理员" not in follow_up.content.decode("utf-8")


@pytest.mark.django_db
def test_auto_register_button_hidden_once_flag_exists(client) -> None:
    SystemConfig.objects.create(
        key=AUTO_REGISTER_BOOTSTRAP_USED_KEY,
        value="true",
        category="general",
        description="test",
        is_secret=False,
        is_active=True,
    )

    response = client.get(reverse("admin_register"))

    assert response.status_code == 200
    assert "自动注册默认超级管理员" not in response.content.decode("utf-8")
