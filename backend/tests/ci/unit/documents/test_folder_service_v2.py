"""template/folder_service.py 补覆盖测试。

FolderTemplateService 为 usecases 薄委托层（验证参数透传），另含
_check_circular_reference / _check_invalid_chars 两个纯逻辑校验器。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.documents.services.template.folder_service import FolderTemplateService


def _make_service() -> tuple[FolderTemplateService, MagicMock]:
    usecases = MagicMock()
    return FolderTemplateService(usecases=usecases), usecases


class TestDelegation:
    def test_validate_and_fix_structure_ids(self):
        svc, usecases = _make_service()
        usecases.validate_and_fix_structure_ids.return_value = (True, {"children": []}, ["修复了重复ID"])
        result = svc.validate_and_fix_structure_ids({"children": []}, template_id=1)
        assert result == (True, {"children": []}, ["修复了重复ID"])
        usecases.validate_and_fix_structure_ids.assert_called_once_with(structure={"children": []}, template_id=1)

    def test_validate_structure_ids(self):
        svc, usecases = _make_service()
        usecases.validate_structure_ids.return_value = (False, ["ID重复"])
        assert svc.validate_structure_ids({"children": []}) == (False, ["ID重复"])

    def test_get_duplicate_id_report(self):
        svc, usecases = _make_service()
        usecases.get_duplicate_id_report.return_value = {"duplicates": []}
        assert svc.get_duplicate_id_report() == {"duplicates": []}

    def test_create_template(self):
        svc, usecases = _make_service()
        tpl = MagicMock()
        usecases.create_template.return_value = tpl
        assert svc.create_template("模板", "civil", "first_trial", {"children": []}, is_default=True) is tpl
        usecases.create_template.assert_called_once_with(
            name="模板",
            case_type="civil",
            case_stage="first_trial",
            structure={"children": []},
            is_default=True,
            is_active=True,
        )

    def test_update_structure(self):
        svc, usecases = _make_service()
        usecases.update_structure.return_value = "updated"
        assert svc.update_structure(3, {"children": []}) == "updated"
        usecases.update_structure.assert_called_once_with(template_id=3, structure={"children": []})

    def test_get_template_for_case(self):
        svc, usecases = _make_service()
        usecases.get_template_for_case.return_value = None
        assert svc.get_template_for_case("civil", "first_trial") is None
        usecases.get_template_for_case.assert_called_once_with(case_type="civil", case_stage="first_trial")

    def test_get_template_by_id(self):
        svc, usecases = _make_service()
        tpl = MagicMock()
        usecases.get_template_by_id.return_value = tpl
        assert svc.get_template_by_id(5) is tpl
        usecases.get_template_by_id.assert_called_once_with(template_id=5)

    def test_validate_structure(self):
        svc, usecases = _make_service()
        usecases.validate_structure.return_value = (True, "")
        assert svc.validate_structure({"children": []}) == (True, "")

    def test_list_templates(self):
        svc, usecases = _make_service()
        usecases.list_templates.return_value = []
        svc.list_templates(template_type="contract", case_type="civil", is_active=True)
        usecases.list_templates.assert_called_once_with(
            template_type="contract", case_type="civil", case_stage=None, is_active=True
        )

    def test_delete_template(self):
        svc, usecases = _make_service()
        usecases.delete_template.return_value = True
        assert svc.delete_template(9) is True
        usecases.delete_template.assert_called_once_with(template_id=9)

    def test_create_template_from_dict(self):
        svc, usecases = _make_service()
        usecases.create_template_from_dict.return_value = "created"
        assert svc.create_template_from_dict({"name": "x"}) == "created"
        usecases.create_template_from_dict.assert_called_once_with(data={"name": "x"})

    def test_update_template_from_dict(self):
        svc, usecases = _make_service()
        usecases.update_template_from_dict.return_value = "updated"
        assert svc.update_template_from_dict(2, {"name": "y"}) == "updated"
        usecases.update_template_from_dict.assert_called_once_with(template_id=2, data={"name": "y"})


class TestCheckCircularReference:
    def setup_method(self):
        self.svc, _ = _make_service()

    def test_no_cycle(self):
        structure = {"children": [{"id": "a", "name": "A", "children": [{"id": "b", "name": "B"}]}]}
        assert self.svc._check_circular_reference(structure) == (False, "")

    def test_cycle_detected(self):
        structure = {
            "children": [
                {"id": "a", "name": "A", "children": [{"id": "a", "name": "A2"}]},
            ]
        }
        has_cycle, path = self.svc._check_circular_reference(structure)
        assert has_cycle is True
        assert "A" in path or "A2" in path

    def test_sibling_same_id_flagged_as_cycle(self):
        """兄弟节点复用同一 id：外层循环共享 visited，会被保守地判为循环。"""
        structure = {"children": [{"id": "a", "name": "A"}, {"id": "a", "name": "A2"}]}
        has_cycle, path = self.svc._check_circular_reference(structure)
        assert has_cycle is True
        assert path == "A2"

    def test_children_not_list_returns_ok(self):
        assert self.svc._check_circular_reference({"children": "not-a-list"}) == (False, "")

    def test_non_dict_child_skipped(self):
        assert self.svc._check_circular_reference({"children": ["junk", {"id": "a", "name": "A"}]}) == (False, "")

    def test_child_without_id_processed(self):
        assert self.svc._check_circular_reference({"children": [{"name": "无ID"}]}) == (False, "")


class TestCheckInvalidChars:
    def setup_method(self):
        self.svc, _ = _make_service()

    def test_valid_names(self):
        structure = {"children": [{"id": "a", "name": "1-立案材料"}]}
        assert self.svc._check_invalid_chars(structure) == (False, "")

    def test_invalid_char_detected(self):
        structure = {"children": [{"id": "a", "name": "非法:名称"}]}
        has_invalid, info = self.svc._check_invalid_chars(structure)
        assert has_invalid is True
        assert "非法:名称" in info

    def test_nested_invalid_char(self):
        structure = {"children": [{"id": "a", "name": "父级", "children": [{"id": "b", "name": "子级?"}]}]}
        has_invalid, info = self.svc._check_invalid_chars(structure)
        assert has_invalid is True
        assert "子级?" in info

    def test_all_invalid_chars_recognized(self):
        for ch in '/*\\:*?"<>|':
            structure = {"children": [{"id": "a", "name": f"X{ch}Y"}]}
            has_invalid, _info = self.svc._check_invalid_chars(structure)
            assert has_invalid is True, f"字符 {ch} 未被识别为非法"

    def test_children_not_list_returns_ok(self):
        assert self.svc._check_invalid_chars({"children": None}) == (False, "")

    def test_empty_name_skipped(self):
        assert self.svc._check_invalid_chars({"children": [{"id": "a", "name": ""}]}) == (False, "")


class TestInvalidCharsPattern:
    def test_pattern_constants(self):
        assert FolderTemplateService.INVALID_CHARS == r'[/\\:*?"<>|]'
        assert FolderTemplateService.INVALID_CHARS_PATTERN.search("a/b")
        assert FolderTemplateService.INVALID_CHARS_PATTERN.search("a\\b")
        assert FolderTemplateService.INVALID_CHARS_PATTERN.findall("a:b") == [":"]
        assert not FolderTemplateService.INVALID_CHARS_PATTERN.search("正常名称")


class TestConstructorRequiresUsecases:
    def test_usecases_keyword_only(self):
        with pytest.raises(TypeError):
            FolderTemplateService(MagicMock())  # type: ignore[misc]
