"""
通用数据验证工具模块
提供常用的验证函数和验证器
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .exceptions import ValidationException


class Validators:
    """通用验证器集合"""

    # 正则表达式模式
    PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    ID_CARD_PATTERN = re.compile(r"^[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$")
    SOCIAL_CREDIT_CODE_PATTERN = re.compile(r"^[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}$")

    @classmethod
    def validate_phone(cls, phone: str | None, field_name: str = "phone") -> str | None:
        """
        验证手机号码

        Args:
            phone: 手机号码
            field_name: 字段名（用于错误信息）

        Returns:
            验证后的手机号码

        Raises:
            ValidationException: 验证失败
        """
        if not phone:
            return None

        phone = phone.strip()
        if not phone:
            return None
        if not cls.PHONE_PATTERN.match(phone):
            raise ValidationException("手机号码格式不正确", errors={field_name: "请输入有效的11位手机号码"})
        return phone

    @classmethod
    def validate_email(cls, email: str | None, field_name: str = "email") -> str | None:
        """验证邮箱地址"""
        if not email:
            return None

        email = email.strip().lower()
        if not cls.EMAIL_PATTERN.match(email):
            raise ValidationException("邮箱格式不正确", errors={field_name: "请输入有效的邮箱地址"})
        return email

    @classmethod
    def validate_id_card(cls, id_card: str | None, field_name: str = "id_card") -> str | None:
        """验证身份证号码"""
        if not id_card:
            return None

        id_card = id_card.strip().upper()
        if not cls.ID_CARD_PATTERN.match(id_card):
            raise ValidationException("身份证号码格式不正确", errors={field_name: "请输入有效的18位身份证号码"})

        # 校验码验证
        if not cls._verify_id_card_checksum(id_card):
            raise ValidationException("身份证号码校验失败", errors={field_name: "身份证号码校验码不正确"})

        return id_card

    @classmethod
    def _verify_id_card_checksum(cls, id_card: str) -> bool:
        """验证身份证校验码"""
        weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        check_codes = "10X98765432"

        try:
            total = sum(int(id_card[i]) * weights[i] for i in range(17))
            return check_codes[total % 11] == id_card[17]
        except (ValueError, IndexError):
            return False

    @classmethod
    def validate_social_credit_code(cls, code: str | None, field_name: str = "social_credit_code") -> str | None:
        """验证统一社会信用代码"""
        if not code:
            return None

        code = code.strip().upper()
        if not cls.SOCIAL_CREDIT_CODE_PATTERN.match(code):
            raise ValidationException(
                "统一社会信用代码格式不正确", errors={field_name: "请输入有效的18位统一社会信用代码"}
            )
        return code

    @classmethod
    def validate_required(cls, value: Any, field_name: str) -> Any:
        """验证必填字段"""
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValidationException(f"{field_name} 不能为空", errors={field_name: "此字段为必填项"})
        return value

    @classmethod
    def validate_length(
        cls,
        value: str | None,
        field_name: str,
        min_length: int | None = None,
        max_length: int | None = None,
    ) -> str | None:
        """验证字符串长度"""
        if value is None or value == "":
            return None

        length = len(value)

        if min_length is not None and length < min_length:
            raise ValidationException(f"{field_name} 长度不足", errors={field_name: f"最少需要 {min_length} 个字符"})

        if max_length is not None and length > max_length:
            raise ValidationException(f"{field_name} 长度超限", errors={field_name: f"最多允许 {max_length} 个字符"})

        return value

    @classmethod
    def validate_range(
        cls,
        value: float | None,
        field_name: str,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> float | None:
        """验证数值范围"""
        if value is None:
            return value

        if min_value is not None and value < min_value:
            raise ValidationException(f"{field_name} 值过小", errors={field_name: f"最小值为 {min_value}"})

        if max_value is not None and value > max_value:
            raise ValidationException(f"{field_name} 值过大", errors={field_name: f"最大值为 {max_value}"})

        return value

    @classmethod
    def validate_decimal(
        cls,
        value: Any,
        field_name: str,
        max_digits: int = 14,
        decimal_places: int = 2,
    ) -> Decimal | None:
        """验证并转换为 Decimal"""
        if value is None:
            return None

        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError) as e:
            raise ValidationException(f"{field_name} 格式不正确", errors={field_name: "请输入有效的数字"}) from e

        # 检查精度
        sign, digits, exponent = decimal_value.as_tuple()
        total_digits = len(digits)
        decimal_digits = -exponent if isinstance(exponent, int) and exponent < 0 else 0
        integer_digits = total_digits - decimal_digits

        if integer_digits + decimal_places > max_digits:
            raise ValidationException(
                f"{field_name} 数值过大", errors={field_name: f"整数部分最多 {max_digits - decimal_places} 位"}
            )

        if decimal_digits > decimal_places:
            raise ValidationException(
                f"{field_name} 小数位数过多", errors={field_name: f"最多保留 {decimal_places} 位小数"}
            )

        return decimal_value

    @classmethod
    def validate_date(
        cls,
        value: Any,
        field_name: str,
        min_date: date | None = None,
        max_date: date | None = None,
    ) -> date | None:
        """验证日期"""
        if value is None:
            return None

        if isinstance(value, datetime):
            value = value.date()
        elif isinstance(value, str):
            try:
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError as e:
                raise ValidationException(
                    f"{field_name} 日期格式不正确", errors={field_name: "请使用 YYYY-MM-DD 格式"}
                ) from e
        elif not isinstance(value, date):
            raise ValidationException(f"{field_name} 类型不正确", errors={field_name: "请提供有效的日期"})

        if min_date and value < min_date:
            raise ValidationException(f"{field_name} 日期过早", errors={field_name: f"日期不能早于 {min_date}"})

        if max_date and value > max_date:
            raise ValidationException(f"{field_name} 日期过晚", errors={field_name: f"日期不能晚于 {max_date}"})

        return value  # type: ignore[no-any-return]

    @classmethod
    def validate_in_choices(
        cls,
        value: Any,
        field_name: str,
        choices: list[Any],
        allow_none: bool = True,
    ) -> Any:
        """验证值是否在选项列表中"""
        if value is None:
            if allow_none:
                return None
            raise ValidationException(f"{field_name} 不能为空", errors={field_name: "此字段为必填项"})

        if value not in choices:
            raise ValidationException(
                f"{field_name} 值无效", errors={field_name: f"有效选项: {', '.join(str(c) for c in choices)}"}
            )

        return value

    # 可执行文件 magic bytes（PE/ELF/Mach-O）
    EXECUTABLE_MAGIC: tuple[bytes, ...] = (
        b"MZ",  # Windows PE
        b"\x7fELF",  # Linux ELF
        b"\xfe\xed\xfa\xce",  # Mach-O 32-bit
        b"\xfe\xed\xfa\xcf",  # Mach-O 64-bit
        b"\xce\xfa\xed\xfe",  # Mach-O 32-bit LE
        b"\xcf\xfa\xed\xfe",  # Mach-O 64-bit LE
    )

    @classmethod
    def validate_uploaded_file(
        cls,
        uploaded_file: Any,
        allowed_extensions: list[str] | None = None,
        max_size_mb: float | None = None,
        max_size_bytes: int | None = None,
        field_name: str = "file",
    ) -> Any:
        """
        验证上传文件的格式和大小

        Args:
            uploaded_file: 上传的文件对象
            allowed_extensions: 允许的扩展名列表，如 [".pdf", ".jpg"]
            max_size_mb: 最大文件大小（MB），None 表示不限制
            max_size_bytes: 最大文件大小（字节），None 表示不限制
            field_name: 字段名（用于错误信息）

        Returns:
            验证通过的文件对象

        Raises:
            ValidationException: 验证失败
        """
        if not uploaded_file:
            raise ValidationException("请选择要上传的文件", errors={field_name: "文件不能为空"})

        if allowed_extensions:
            filename: str = getattr(uploaded_file, "name", "") or ""
            ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
            if ext not in allowed_extensions:
                raise ValidationException(
                    f"不支持的文件格式: {ext}",
                    errors={field_name: f"允许的格式: {', '.join(allowed_extensions)}"},
                )

        size: int = getattr(uploaded_file, "size", 0) or 0
        if max_size_bytes is not None and size > max_size_bytes:
            raise ValidationException(
                "文件大小超限",
                errors={field_name: f"文件大小不能超过 {max_size_bytes} 字节"},
            )
        if max_size_mb is not None and size > max_size_mb * 1024 * 1024:
            raise ValidationException(
                "文件大小超限",
                errors={field_name: f"文件大小不能超过 {max_size_mb} MB"},
            )

        # 检测可执行文件 magic bytes
        try:
            header: bytes = uploaded_file.read(8)
            uploaded_file.seek(0)
            if any(header.startswith(magic) for magic in cls.EXECUTABLE_MAGIC):
                raise ValidationException(
                    "不允许上传可执行文件",
                    errors={field_name: "文件内容被识别为可执行文件"},
                )
        except (AttributeError, OSError):
            pass

        return uploaded_file
