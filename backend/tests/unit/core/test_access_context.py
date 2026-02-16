from unittest.mock import MagicMock

from django.test import TestCase

from apps.core.security import AccessContext, get_request_access_context


class AccessContextTest(TestCase):
    def test_returns_existing_access_ctx(self):
        request = MagicMock()
        ctx = AccessContext(user="u", org_access={"k": 1}, perm_open_access=True)
        request.access_ctx = ctx
        self.assertIs(get_request_access_context(request), ctx)

    def test_builds_context_from_request_fields(self):
        request = MagicMock()
        request.user = "u"
        request.org_access = {"k": 1}
        request.perm_open_access = True
        ctx = get_request_access_context(request)
        self.assertEqual(ctx.user, "u")
        self.assertEqual(ctx.org_access, {"k": 1})
        self.assertTrue(ctx.perm_open_access)
