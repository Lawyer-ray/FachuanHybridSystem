"""Batch 6 coverage tests for image_rotation module."""

from __future__ import annotations

import base64

import pytest

from apps.core.exceptions import ValidationException


class TestValidation:
    def test_decode_base64_payload(self):
        from apps.image_rotation.services.validation import decode_base64_payload

        data = base64.b64encode(b"test image data").decode()
        result = decode_base64_payload(data)
        assert result == b"test image data"

    def test_decode_base64_with_prefix(self):
        from apps.image_rotation.services.validation import decode_base64_payload

        raw = base64.b64encode(b"test").decode()
        data = f"data:image/png;base64,{raw}"
        result = decode_base64_payload(data)
        assert result == b"test"

    def test_decode_base64_empty(self):
        from apps.image_rotation.services.validation import decode_base64_payload

        result = decode_base64_payload("")
        assert result == b""

    def test_decode_base64_none(self):
        from apps.image_rotation.services.validation import decode_base64_payload

        result = decode_base64_payload(None)
        assert result == b""

    def test_decode_base64_invalid(self):
        from apps.image_rotation.services.validation import decode_base64_payload

        with pytest.raises(ValidationException):
            decode_base64_payload("!!!invalid!!!")

    def test_validate_image_format_valid(self):
        from apps.image_rotation.services.validation import validate_image_format

        result = validate_image_format(img_format="jpeg", supported_formats={"jpeg", "png"})
        assert result == "jpeg"

    def test_validate_image_format_case_insensitive(self):
        from apps.image_rotation.services.validation import validate_image_format

        result = validate_image_format(img_format="PNG", supported_formats={"jpeg", "png"})
        assert result == "png"

    def test_validate_image_format_default(self):
        from apps.image_rotation.services.validation import validate_image_format

        result = validate_image_format(img_format="", supported_formats={"jpeg", "png"})
        assert result == "jpeg"

    def test_validate_image_format_unsupported(self):
        from apps.image_rotation.services.validation import validate_image_format

        with pytest.raises(ValidationException):
            validate_image_format(img_format="bmp", supported_formats={"jpeg", "png"})

    def test_validate_file_size_ok(self):
        from apps.image_rotation.services.validation import validate_file_size

        validate_file_size(image_bytes=b"small", max_file_size=1024)  # no error

    def test_validate_file_size_too_large(self):
        from apps.image_rotation.services.validation import validate_file_size

        with pytest.raises(ValidationException):
            validate_file_size(image_bytes=b"x" * 2000, max_file_size=1024)
