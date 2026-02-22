from django.test import TestCase

from apps.core.filesystem import BaseFolderBindingService


class _FakeFilesystemService:
    def __init__(self, ok: bool = True):
        self.ok = ok
        self.calls: list[tuple[str, ...]] = []

    def ensure_subdirectories(self, base_path, subdirs):
        self.calls.append((base_path, list(subdirs)))
        return self.ok


class _Svc(BaseFolderBindingService):
    DEFAULT_SUBDIRS = {"a": "AA", "b": "BB"}


class BaseFolderBindingServiceTest(TestCase):
    def test_ensure_subdirectories_delegates_to_filesystem_service(self):
        fs = _FakeFilesystemService(ok=True)
        svc = _Svc(filesystem_service=fs)
        ok = svc.ensure_subdirectories("/tmp/test-base-folder-binding")
        self.assertTrue(ok)
        self.assertEqual(fs.calls, [("/tmp/test-base-folder-binding", ["AA", "BB"])])

    def test_format_path_for_display(self):
        svc = _Svc(filesystem_service=_FakeFilesystemService())
        path = "/a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p/q/r/s/t/u/v/w/x/y/z"
        out = svc.format_path_for_display(path, max_length=20)
        self.assertLessEqual(len(out), 20)
        self.assertIn("...", out)
