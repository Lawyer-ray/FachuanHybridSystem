"""OA 立案异常与常量单元测试。"""
from __future__ import annotations

import pytest

from apps.oa_filing.services.exceptions import OAFilingError, ScriptExecutionError


def test_oa_filing_error_default_message() -> None:
    """默认消息。"""
    err = OAFilingError()
    assert err.message == ""
    assert str(err) == ""


def test_oa_filing_error_custom_message() -> None:
    """自定义消息。"""
    err = OAFilingError("立案失败")
    assert err.message == "立案失败"
    assert str(err) == "立案失败"


def test_oa_filing_error_is_exception() -> None:
    """是 Exception 的子类。"""
    assert issubclass(OAFilingError, Exception)
    with pytest.raises(OAFilingError):
        raise OAFilingError("test")


def test_script_execution_error_default() -> None:
    """默认消息。"""
    err = ScriptExecutionError()
    assert err.message == "脚本执行失败"


def test_script_execution_error_custom() -> None:
    """自定义消息。"""
    err = ScriptExecutionError("自定义错误")
    assert err.message == "自定义错误"


def test_script_execution_error_is_oa_filing_error() -> None:
    """是 OAFilingError 的子类。"""
    assert issubclass(ScriptExecutionError, OAFilingError)
    with pytest.raises(OAFilingError):
        raise ScriptExecutionError("test")
