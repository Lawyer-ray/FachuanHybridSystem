import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


class NoServiceLocatorRegressionsTest(unittest.TestCase):
    def _read(self, relative_path: str) -> str:
        return (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    def _assert_not_contains(self, *, path: str, needle: str) -> None:
        content = self._read(path)
        self.assertNotIn(needle, content, msg=f"{needle} found in {path}")

    def test_llm_common_has_no_servicelocator(self):
        self._assert_not_contains(path="apps/core/api/llm_common.py", needle="ServiceLocator")

    def test_auto_token_acquisition_service_has_no_servicelocator(self):
        self._assert_not_contains(
            path="apps/automation/services/token/auto_token_acquisition_service.py",
            needle="ServiceLocator",
        )

    def test_contract_folder_binding_service_has_no_servicelocator(self):
        self._assert_not_contains(
            path="apps/contracts/services/folder/folder_binding_service.py", needle="ServiceLocator"
        )

    def test_document_delivery_schedule_entrypoints_have_no_servicelocator(self):
        self._assert_not_contains(path="apps/automation/api/document_delivery_api.py", needle="ServiceLocator")
        self._assert_not_contains(
            path="apps/automation/admin/document_delivery/document_delivery_schedule_admin.py",
            needle="ServiceLocator",
        )
