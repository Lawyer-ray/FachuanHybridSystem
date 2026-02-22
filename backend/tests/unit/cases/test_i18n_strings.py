"""单元测试：i18n 包裹后字符串可正常显示。

验证 gettext_lazy 包裹的字符串在中英文 locale 下正常渲染。

验证: 需求 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

from __future__ import annotations

from django.utils.functional import Promise
from django.utils.translation import override


class TestValidateCaseLogAttachmentI18n:
    """验证 utils.validate_case_log_attachment 错误消息是 lazy string。"""

    def test_unsupported_type_is_lazy(self) -> None:
        from apps.cases.utils import validate_case_log_attachment

        _ok, msg = validate_case_log_attachment("bad.exe", None)
        assert msg is not None
        assert isinstance(msg, Promise)

    def test_unsupported_type_str_zh(self) -> None:
        from apps.cases.utils import validate_case_log_attachment

        _ok, msg = validate_case_log_attachment("bad.exe", None)
        assert msg is not None
        with override("zh-hans"):
            rendered = str(msg)
        assert isinstance(rendered, str)
        assert len(rendered) > 0

    def test_file_too_large_is_lazy(self) -> None:
        from apps.cases.utils import validate_case_log_attachment

        _ok, msg = validate_case_log_attachment("ok.pdf", 999_999_999)
        assert msg is not None
        assert isinstance(msg, Promise)

    def test_file_too_large_str_zh(self) -> None:
        from apps.cases.utils import validate_case_log_attachment

        _ok, msg = validate_case_log_attachment("ok.pdf", 999_999_999)
        assert msg is not None
        with override("zh-hans"):
            rendered = str(msg)
        assert isinstance(rendered, str)
        assert len(rendered) > 0


class TestNormalizeStagesI18n:
    """验证 domain/validators.normalize_stages ValueError 消息是 lazy string。"""

    def test_strict_not_applicable_raises_lazy(self) -> None:
        from apps.cases.domain.validators import normalize_stages

        try:
            normalize_stages("INVALID_TYPE", ["s1"], None, strict=True)
        except ValueError as exc:
            msg = exc.args[0]
            assert isinstance(msg, Promise)
            rendered = str(msg)
            assert isinstance(rendered, str)
            assert len(rendered) > 0
        else:
            # normalize_stages 对不适用类型 + strict 应抛出 ValueError
            raise AssertionError("Expected ValueError was not raised")  # noqa: TC003

    def test_invalid_stage_raises_lazy(self) -> None:
        from apps.cases.domain.validators import normalize_stages

        try:
            normalize_stages("civil", ["first_trial"], "BOGUS_CUR")
        except ValueError as exc:
            msg = exc.args[0]
            assert isinstance(msg, Promise)
            rendered = str(msg)
            assert isinstance(rendered, str)
            assert len(rendered) > 0
        else:
            raise AssertionError("Expected ValueError was not raised")  # noqa: TC003


class TestLazyStringStrConversion:
    """验证 lazy string 可被 str() 正常转换，不会报错。"""

    def test_str_conversion_en(self) -> None:
        from apps.cases.utils import validate_case_log_attachment

        _ok, msg = validate_case_log_attachment("bad.exe", None)
        assert msg is not None
        with override("en"):
            rendered = str(msg)
        assert isinstance(rendered, str)
        assert len(rendered) > 0

    def test_str_conversion_zh(self) -> None:
        from apps.cases.utils import validate_case_log_attachment

        _ok, msg = validate_case_log_attachment("bad.exe", None)
        assert msg is not None
        with override("zh-hans"):
            rendered = str(msg)
        assert isinstance(rendered, str)
        assert len(rendered) > 0
