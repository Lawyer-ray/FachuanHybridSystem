"""API schemas and serializers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from apps.core.config.exceptions import ConfigFileError, ConfigValidationError

ALLOWED_CASE_TYPE_CODES = {
    "civil",
    "criminal",
    "administrative",
    "labor",
    "intl",
    "special",
    "advisor",
}


class StageRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    applicable_case_types: list[str] = Field(default_factory=list)


class LegalStatusRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    applicable_case_types: list[str] = Field(default_factory=list)


class LegalStatusCompatibilityRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    group: str
    compatible_statuses: list[str] | None = None


class BusinessRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_stages: list[StageRule] = Field(default_factory=list)
    legal_statuses: list[LegalStatusRule] = Field(default_factory=list)
    legal_status_compatibility: dict[str, LegalStatusCompatibilityRule] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_semantics(self) -> BusinessRules:
        errors: list[str] = []
        self._check_stage_duplicates(errors)
        self._check_status_duplicates(errors)
        status_value_set = {s.value for s in self.legal_statuses}
        self._check_stage_case_types(errors)
        self._check_status_case_types(errors)
        self._check_compatibility_refs(errors, status_value_set)
        if errors:
            raise ValueError("; ".join(errors))
        return self

    def _check_stage_duplicates(self, errors: list[str]) -> None:
        stage_values = [s.value for s in self.case_stages]
        if len(stage_values) != len(set(stage_values)):
            errors.append("case_stages.value 存在重复值")

    def _check_status_duplicates(self, errors: list[str]) -> None:
        status_values = [s.value for s in self.legal_statuses]
        if len(status_values) != len(set(status_values)):
            errors.append("legal_statuses.value 存在重复值")

    def _check_stage_case_types(self, errors: list[str]) -> None:
        for idx, stage in enumerate(self.case_stages):
            invalid = [t for t in stage.applicable_case_types if t not in ALLOWED_CASE_TYPE_CODES]
            if invalid:
                errors.append(f"case_stages[{idx}].applicable_case_types 包含未知类型: {', '.join(invalid)}")

    def _check_status_case_types(self, errors: list[str]) -> None:
        for idx, status in enumerate(self.legal_statuses):
            invalid = [t for t in status.applicable_case_types if t not in ALLOWED_CASE_TYPE_CODES]
            if invalid:
                errors.append(f"legal_statuses[{idx}].applicable_case_types 包含未知类型: {', '.join(invalid)}")

    def _check_compatibility_refs(self, errors: list[str], status_value_set: set[str]) -> None:
        for key, rule in self.legal_status_compatibility.items():
            if key not in status_value_set:
                errors.append(f"legal_status_compatibility 包含未知 key: {key}")
                continue
            if rule.value != key:
                errors.append(f"legal_status_compatibility[{key}].value 必须等于其 key")
            if rule.compatible_statuses is not None:
                unknown = [s for s in rule.compatible_statuses if s not in status_value_set]
                if unknown:
                    errors.append(
                        f"legal_status_compatibility[{key}].compatible_statuses 引用未知诉讼地位: {', '.join(unknown)}"
                    )


def load_business_rules(config_path: Path | None = None) -> BusinessRules:
    path = config_path or (Path(__file__).resolve().parents[1] / "business_rules.yaml")
    if not path.exists():
        raise ConfigFileError(str(path), message="配置文件不存在")

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        line_no = mark.line + 1 if mark else None
        raise ConfigFileError(str(path), line=line_no, message=f"YAML 格式错误: {e}", original_error=e) from e
    except Exception as e:
        raise ConfigFileError(str(path), message="读取配置文件失败", original_error=e) from e

    if not isinstance(data, dict):
        raise ConfigValidationError(errors=["YAML 顶层必须是对象(mapping)"], key=str(path))

    try:
        return BusinessRules.model_validate(data)
    except ValidationError as e:
        errors: list[Any] = []
        for item in e.errors():
            loc = ".".join(str(p) for p in item.get("loc", []))
            msg = item.get("msg", "")
            errors.append(f"{loc}: {msg}" if loc else msg)
        raise ConfigValidationError(errors=errors, key=str(path)) from e
    except ValueError as e:
        raise ConfigValidationError(errors=[str(e)], key=str(path)) from e
