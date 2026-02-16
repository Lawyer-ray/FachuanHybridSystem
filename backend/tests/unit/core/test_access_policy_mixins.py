from django.test import TestCase

from apps.core.exceptions import ForbiddenError
from apps.core.security import DjangoPermsMixin


class _User:
    def __init__(self, *, is_authenticated: bool, is_admin: bool = False, is_superuser: bool = False):
        self.is_authenticated = is_authenticated
        self.is_admin = is_admin
        self.is_superuser = is_superuser


class AccessPolicyMixinsTest(TestCase):
    def test_ensure_admin_allows_open_access_without_user(self):
        mixin = DjangoPermsMixin()
        mixin.ensure_admin(None, perm_open_access=True)

    def test_ensure_admin_requires_authentication(self):
        mixin = DjangoPermsMixin()
        with self.assertRaises(ForbiddenError):
            mixin.ensure_admin(_User(is_authenticated=False), perm_open_access=False)

    def test_ensure_admin_requires_admin_or_superuser(self):
        mixin = DjangoPermsMixin()
        with self.assertRaises(ForbiddenError):
            mixin.ensure_admin(_User(is_authenticated=True, is_admin=False, is_superuser=False), perm_open_access=False)

    def test_ensure_admin_allows_admin(self):
        mixin = DjangoPermsMixin()
        mixin.ensure_admin(_User(is_authenticated=True, is_admin=True), perm_open_access=False)

    def test_ensure_admin_allows_superuser(self):
        mixin = DjangoPermsMixin()
        mixin.ensure_admin(_User(is_authenticated=True, is_superuser=True), perm_open_access=False)
