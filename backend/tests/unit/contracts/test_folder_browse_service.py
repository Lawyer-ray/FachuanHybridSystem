import tempfile

from django.test import SimpleTestCase, override_settings

from apps.contracts.services.folder_binding_service import FolderBindingService
from apps.core.exceptions import ValidationException
from pathlib import Path


class FolderBrowseServiceTests(SimpleTestCase):
    def setUp(self):
        self.service = FolderBindingService()

    def test_list_subdirs_only_returns_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "a").mkdir()
            (root / "b").mkdir()
            (root / "f.txt").write_text("x", encoding="utf-8")

            with override_settings(FOLDER_BROWSE_ROOTS=[str(root)]):
                entries = self.service.list_subdirs(str(root))
                names = {e["name"] for e in entries}
                self.assertEqual(names, {"a", "b"})

    def test_resolve_outside_root_is_forbidden(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outside = root.parent

            with override_settings(FOLDER_BROWSE_ROOTS=[str(root)]):
                with self.assertRaises(ValidationException) as ctx:
                    self.service.resolve_under_allowed_roots(str(outside))
                self.assertEqual(ctx.exception.code, "BROWSE_FORBIDDEN")

    def test_resolve_network_path_is_not_supported_for_browse(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with override_settings(FOLDER_BROWSE_ROOTS=[str(root)]):
                with self.assertRaises(ValidationException) as ctx:
                    self.service.resolve_under_allowed_roots("smb://server/share")
                self.assertEqual(ctx.exception.code, "BROWSE_NOT_SUPPORTED")
