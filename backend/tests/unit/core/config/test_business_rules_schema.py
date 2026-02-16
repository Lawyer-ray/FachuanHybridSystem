from __future__ import annotations

from pathlib import Path

import pytest

from apps.core.config.exceptions import ConfigFileError, ConfigValidationError
from apps.core.config.schemas.business_rules import load_business_rules


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_load_business_rules_valid(tmp_path: Path):
    path = _write(
        tmp_path,
        "business_rules.yaml",
        """
case_stages:
  - value: filing
    label: 立案
legal_statuses:
  - value: PLAINTIFF
    label: 原告
legal_status_compatibility:
  PLAINTIFF:
    value: PLAINTIFF
    label: 原告
    group: OUR
    compatible_statuses: null
""".lstrip(),
    )

    rules = load_business_rules(path)
    assert len(rules.case_stages) == 1
    assert len(rules.legal_statuses) == 1
    assert "PLAINTIFF" in rules.legal_status_compatibility


def test_load_business_rules_requires_mapping_top_level(tmp_path: Path):
    path = _write(tmp_path, "business_rules.yaml", "[]\n")
    with pytest.raises(ConfigValidationError):
        load_business_rules(path)


def test_load_business_rules_detects_duplicate_values(tmp_path: Path):
    path = _write(
        tmp_path,
        "business_rules.yaml",
        """
case_stages:
  - value: filing
    label: 立案
  - value: filing
    label: 立案-重复
legal_statuses: []
legal_status_compatibility: {}
""".lstrip(),
    )
    with pytest.raises(ConfigValidationError) as exc:
        load_business_rules(path)
    assert "重复" in str(exc.value)


def test_load_business_rules_detects_unknown_compatibility_key(tmp_path: Path):
    path = _write(
        tmp_path,
        "business_rules.yaml",
        """
case_stages: []
legal_statuses:
  - value: A
    label: A
legal_status_compatibility:
  B:
    value: B
    label: B
    group: OUR
    compatible_statuses: null
""".lstrip(),
    )
    with pytest.raises(ConfigValidationError) as exc:
        load_business_rules(path)
    assert "未知" in str(exc.value)
    assert "B" in str(exc.value)


def test_load_business_rules_yaml_syntax_error(tmp_path: Path):
    path = _write(tmp_path, "business_rules.yaml", "case_stages: [\n")
    with pytest.raises(ConfigFileError) as exc:
        load_business_rules(path)
    assert exc.value.line is not None
