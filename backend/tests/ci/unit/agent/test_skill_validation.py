"""技能表单校验：slug / 保留名 / 单行描述 / 正文字节上限 / 归一化。

校验是「用户能把什么写进系统提示」的唯一闸门，所以每条规则都单独断言，
尤其是保留名（内置技能名不得被个人技能占用，否则 ``/skill:`` 会静默顶掉
随代码发布的那份）。
"""

from __future__ import annotations

import pytest

from apps.agent.services.skills import constants, validation


def _payload(**overrides: str) -> dict[str, str]:
    base = {
        "name": "contract-review",
        "title": "合同审查",
        "description": "审查合同时按三段式给出结论",
        "body": "# 做法\n1. 先看主体\n2. 再看违约",
    }
    base.update(overrides)
    return base


def _fields(errors: list[dict[str, str]]) -> list[str]:
    return [error["field"] for error in errors]


class TestName:
    @pytest.mark.parametrize(
        "bad_name",
        ["合同审查", "Contract-Review", "../escape", "a b", "-leading-dash", "x" * 65, "名"],
    )
    def test_rejects_illegal_slug(self, bad_name: str) -> None:
        errors = validation.validate_payload(_payload(name=bad_name))
        assert _fields(errors) == ["name"]
        assert "技能名" in errors[0]["message"]

    @pytest.mark.parametrize("reserved", ["web-research", "deadline-queries", "compact", "manage-skills"])
    def test_rejects_reserved_names(self, reserved: str) -> None:
        errors = validation.validate_payload(_payload(name=reserved))
        assert _fields(errors) == ["name"]
        assert "保留名" in errors[0]["message"]

    def test_rejects_name_taken_by_same_lawyer(self) -> None:
        errors = validation.validate_payload(_payload(name="my-skill"), taken_names={"my-skill"})
        assert _fields(errors) == ["name"]
        assert "同名" in errors[0]["message"]

    def test_name_optional_for_create_when_require_name_false(self) -> None:
        assert validation.validate_payload(_payload(name=""), require_name=False) == []

    def test_name_required_by_default(self) -> None:
        assert _fields(validation.validate_payload(_payload(name=""))) == ["name"]


class TestTitleAndDescription:
    @pytest.mark.parametrize("title", ["", "x" * (constants.MAX_TITLE + 1)])
    def test_rejects_bad_title(self, title: str) -> None:
        assert _fields(validation.validate_payload(_payload(title=title))) == ["title"]

    def test_rejects_empty_description(self) -> None:
        assert _fields(validation.validate_payload(_payload(description=""))) == ["description"]

    def test_rejects_multiline_description(self) -> None:
        errors = validation.validate_payload(_payload(description="第一行\n第二行"))
        assert errors == [{"field": "description", "message": "描述必须是单行（会写进系统提示）"}]

    def test_rejects_too_long_description(self) -> None:
        errors = validation.validate_payload(_payload(description="d" * (constants.MAX_DESCRIPTION + 1)))
        assert _fields(errors) == ["description"]


class TestBody:
    def test_rejects_empty_body(self) -> None:
        assert _fields(validation.validate_payload(_payload(body=""))) == ["body"]

    def test_rejects_body_over_limit(self) -> None:
        errors = validation.validate_payload(_payload(body="x" * (constants.MAX_BODY_BYTES + 1)))
        assert _fields(errors) == ["body"]
        assert "32 KB" in errors[0]["message"]

    def test_accepts_exact_limit(self) -> None:
        assert validation.validate_payload(_payload(body="x" * constants.MAX_BODY_BYTES)) == []


class TestNormalize:
    def test_strips_whitespace_and_normalizes_body(self) -> None:
        normalized = validation.normalize_payload(
            name=" mine ",
            title=" 我的技能 ",
            description=" 单行描述 ",
            body="\ufeff# 标题\r\n1. 步骤\r2. 收尾",
        )
        assert normalized == {
            "name": "mine",
            "title": "我的技能",
            "description": "单行描述",
            "body": "# 标题\n1. 步骤\n2. 收尾",
        }

    def test_keeps_newline_for_validation_to_reject(self) -> None:
        """描述里的换行不能被静默折叠——否则「单行」校验永远看不到它。"""
        normalized = validation.normalize_payload(name="mine", title="t", description="第一行\n第二行", body="b")
        assert "\n" in normalized["description"]
        assert validation.validate_payload(normalized) != []
