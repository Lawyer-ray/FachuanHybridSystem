"""lawyer/lawyer_info_service.py 补覆盖测试。

纯逻辑占位符服务：律师姓名格式化（主办在前）、主办/协办拆分、姓名兜底链路。
全部用 SimpleNamespace 构造合同与律师分配替身，不触碰数据库。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.documents.services.placeholders.lawyer.lawyer_info_service import LawyerInfoService


def _assignment(
    name: str,
    *,
    is_primary: bool,
    has_is_primary_attr: bool = True,
    lawyer_id: int = 1,
    username: str | None = None,
) -> SimpleNamespace:
    lawyer = SimpleNamespace(
        real_name=name, username=username if username is not None else f"user{lawyer_id}", id=lawyer_id
    )
    attrs: dict = {"lawyer": lawyer}
    if has_is_primary_attr:
        attrs["is_primary"] = is_primary
    return SimpleNamespace(id=lawyer_id, **attrs)


def _contract_with(assignments: list) -> SimpleNamespace:
    return SimpleNamespace(id=1, assignments=SimpleNamespace(all=lambda: assignments))


class TestGenerate:
    def test_no_contract_returns_empty(self):
        assert LawyerInfoService().generate({}) == {}

    def test_with_contract_produces_all_keys(self):
        svc = LawyerInfoService()
        contract = _contract_with(
            [
                _assignment("张主办", is_primary=True, lawyer_id=1),
                _assignment("李协办", is_primary=False, lawyer_id=2),
            ]
        )
        result = svc.generate({"contract": contract})
        assert result["律师姓名"] == "张主办、李协办"
        assert result["主办律师"] == "张主办"
        assert result["协办律师"] == "李协办"

    def test_assignments_fetch_error_propagates(self):
        def _raise():
            raise RuntimeError("db error")

        contract = SimpleNamespace(id=1, assignments=SimpleNamespace(all=_raise))
        with pytest.raises(RuntimeError, match="db error"):
            LawyerInfoService().generate({"contract": contract})


class TestGetLawyerAssignments:
    def test_returns_all_assignments(self):
        a1, a2 = _assignment("A", is_primary=True), _assignment("B", is_primary=False)
        contract = _contract_with([a1, a2])
        result = LawyerInfoService()._get_lawyer_assignments(contract)
        assert result == [a1, a2]


class TestFormatLawyerNames:
    def test_empty_returns_empty_string(self):
        assert LawyerInfoService().format_lawyer_names([]) == ""

    def test_primary_first_then_assistants(self):
        svc = LawyerInfoService()
        result = svc.format_lawyer_names(
            [
                _assignment("协办A", is_primary=False, lawyer_id=2),
                _assignment("主办B", is_primary=True, lawyer_id=1),
                _assignment("协办C", is_primary=False, lawyer_id=3),
            ]
        )
        assert result == "主办B、协办A、协办C"

    def test_blank_name_falls_back_to_username(self):
        svc = LawyerInfoService()
        result = svc.format_lawyer_names(
            [
                _assignment("主办", is_primary=True, lawyer_id=1),
                _assignment("", username="zhangsan", is_primary=False, lawyer_id=2),
            ]
        )
        assert result == "主办、zhangsan"

    def test_fully_blank_name_skipped(self):
        svc = LawyerInfoService()
        result = svc.format_lawyer_names(
            [
                _assignment("主办", is_primary=True, lawyer_id=1),
                _assignment("", username="", is_primary=False, lawyer_id=2),
            ]
        )
        assert result == "主办"

    def test_assignment_without_is_primary_attr_treated_as_assistant(self):
        svc = LawyerInfoService()
        result = svc.format_lawyer_names(
            [
                _assignment("主办", is_primary=True, lawyer_id=1),
                _assignment("无标记", is_primary=False, has_is_primary_attr=False, lawyer_id=2),
            ]
        )
        assert result == "主办、无标记"


class TestGetPrimaryLawyerName:
    def test_returns_first_primary(self):
        svc = LawyerInfoService()
        assignments = [
            _assignment("协办", is_primary=False, lawyer_id=1),
            _assignment("主办", is_primary=True, lawyer_id=2),
        ]
        assert svc._get_primary_lawyer_name(assignments) == "主办"

    def test_falls_back_to_first_when_no_primary(self):
        svc = LawyerInfoService()
        assignments = [
            _assignment("甲", is_primary=False, lawyer_id=1),
            _assignment("乙", is_primary=False, lawyer_id=2),
        ]
        assert svc._get_primary_lawyer_name(assignments) == "甲"

    def test_empty_returns_empty(self):
        assert LawyerInfoService()._get_primary_lawyer_name([]) == ""


class TestGetAssistantLawyerNames:
    def test_only_non_primary_included(self):
        svc = LawyerInfoService()
        assignments = [
            _assignment("主办", is_primary=True, lawyer_id=1),
            _assignment("协办A", is_primary=False, lawyer_id=2),
            _assignment("协办B", is_primary=False, lawyer_id=3),
        ]
        assert svc._get_assistant_lawyer_names(assignments) == "协办A、协办B"

    def test_no_assistants_returns_empty(self):
        assignments = [_assignment("主办", is_primary=True, lawyer_id=1)]
        assert LawyerInfoService()._get_assistant_lawyer_names(assignments) == ""


class TestGetLawyerName:
    def test_real_name_preferred(self):
        assignment = _assignment("张三", is_primary=True)
        assert LawyerInfoService()._get_lawyer_name(assignment) == "张三"

    def test_blank_real_name_falls_back_to_username(self):
        lawyer = SimpleNamespace(real_name="   ", username="zhangsan", id=1)
        assignment = SimpleNamespace(id=1, lawyer=lawyer, is_primary=True)
        assert LawyerInfoService()._get_lawyer_name(assignment) == "zhangsan"

    def test_real_name_none_falls_back_to_username(self):
        lawyer = SimpleNamespace(real_name=None, username="lisi", id=1)
        assignment = SimpleNamespace(id=1, lawyer=lawyer, is_primary=True)
        assert LawyerInfoService()._get_lawyer_name(assignment) == "lisi"

    def test_both_blank_returns_empty(self):
        lawyer = SimpleNamespace(real_name="", username="", id=1)
        assignment = SimpleNamespace(id=1, lawyer=lawyer, is_primary=True)
        assert LawyerInfoService()._get_lawyer_name(assignment) == ""

    def test_missing_lawyer_returns_empty(self):
        assignment = SimpleNamespace(id=1, lawyer=None, is_primary=True)
        assert LawyerInfoService()._get_lawyer_name(assignment) == ""

    def test_lawyer_property_raises_returns_empty(self):
        class Boom:
            @property
            def lawyer(self):
                raise RuntimeError("broken relation")

        assert LawyerInfoService()._get_lawyer_name(Boom()) == ""


class TestServiceMetadata:
    def test_placeholder_keys(self):
        assert LawyerInfoService.placeholder_keys == ["律师姓名", "主办律师", "协办律师"]
        assert LawyerInfoService.name == "lawyer_info_service"
        assert LawyerInfoService.category == "lawyer"
