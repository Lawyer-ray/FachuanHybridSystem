from apps.documents.services.folder_template.structure_rules import FolderTemplateStructureRules


class FakeIdService:
    def __init__(self):
        self.replaced = False

    def collect_structure_ids(self, structure):
        return ["a", "a", "b"]

    def find_internal_duplicates(self, ids):
        return {"a"}

    def find_global_duplicates(self, ids, template_id=None):
        return set()

    def replace_duplicate_ids_in_structure(self, structure, duplicate_ids):
        self.replaced = True
        for child in structure.get("children", []):
            if child.get("id") in duplicate_ids:
                child["id"] = "new_id"


def test_validate_structure_ids_detects_internal_duplicates():
    rules = FolderTemplateStructureRules(id_service=FakeIdService())
    ok, errors = rules.validate_structure_ids({"children": [{"id": "a"}, {"id": "a"}]})
    assert ok is False
    assert any("重复ID" in x for x in errors)


def test_validate_and_fix_structure_ids_returns_fixed_copy():
    id_service = FakeIdService()
    rules = FolderTemplateStructureRules(id_service=id_service)
    original = {"children": [{"id": "a"}, {"id": "b"}]}
    fixed, fixed_structure, messages = rules.validate_and_fix_structure_ids(original)

    assert fixed is True
    assert original["children"][0]["id"] == "a"
    assert fixed_structure["children"][0]["id"] == "new_id"
    assert id_service.replaced is True
    assert messages and "已自动修复" in messages[0]
