"""
通用数据验证工具模块
提供常用的验证函数和验证器
"""
import re
from typing import Optional, List, Any
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .exceptions import ValidationException


class Validators:
    """通用验证器集合"""

    # 正则表达式模式
    PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    ID_CARD_PATTERN = re.compile(r"^[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$")
    SOCIAL_CREDIT_CODE_PATTERN = re.compile(r"^[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}$")

    @classmethod
    def validate_phone(cls, phone: Optional[str], field_name: str = "phone") -> Optional[str]:
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
        if not cls.PHONE_PATTERN.match(phone):
            raise ValidationException(
                "手机号码格式不正确",
                errors={field_name: "请输入有效的11位手机号码"}
            )
        return phone

    @classmethod
    def validate_email(cls, email: Optional[str], field_name: str = "email") -> Optional[str]:
        """验证邮箱地址"""
        if not email:
            return None

        email = email.strip().lower()
        if not cls.EMAIL_PATTERN.match(email):
            raise ValidationException(
                "邮箱格式不正确",
                errors={field_name: "请输入有效的邮箱地址"}
            )
        return email

    @classmethod
    def validate_id_card(cls, id_card: Optional[str], field_name: str = "id_card") -> Optional[str]:
        """验证身份证号码"""
        if not id_card:
            return None

        id_card = id_card.strip().upper()
        if not cls.ID_CARD_PATTERN.match(id_card):
            raise ValidationException(
                "身份证号码格式不正确",
                errors={field_name: "请输入有效的18位身份证号码"}
            )

        # 校验码验证
        if not cls._verify_id_card_checksum(id_card):
            raise ValidationException(
                "身份证号码校验失败",
                errors={field_name: "身份证号码校验码不正确"}
            )

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
    def validate_social_credit_code(
        cls, code: Optional[str], field_name: str = "social_credit_code"
    ) -> Optional[str]:
        """验证统一社会信用代码"""
        if not code:
            return None

        code = code.strip().upper()
        if not cls.SOCIAL_CREDIT_CODE_PATTERN.match(code):
            raise ValidationException(
                "统一社会信用代码格式不正确",
                errors={field_name: "请输入有效的18位统一社会信用代码"}
            )
        return code

    @classmethod
    def validate_required(cls, value: Any, field_name: str) -> Any:
        """验证必填字段"""
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValidationException(
                f"{field_name} 不能为空",
                errors={field_name: "此字段为必填项"}
            )
        return value

    @classmethod
    def validate_length(
        cls,
        value: Optional[str],
        field_name: str,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> Optional[str]:
        """验证字符串长度"""
        if not value:
            return value

        length = len(value)

        if min_length is not None and length < min_length:
            raise ValidationException(
                f"{field_name} 长度不足",
                errors={field_name: f"最少需要 {min_length} 个字符"}
            )

        if max_length is not None and length > max_length:
            raise ValidationException(
                f"{field_name} 长度超限",
                errors={field_name: f"最多允许 {max_length} 个字符"}
            )

        return value

    @classmethod
    def validate_range(
        cls,
        value: Optional[float],
        field_name: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ) -> Optional[float]:
        """验证数值范围"""
        if value is None:
            return value

        if min_value is not None and value < min_value:
            raise ValidationException(
                f"{field_name} 值过小",
                errors={field_name: f"最小值为 {min_value}"}
            )

        if max_value is not None and value > max_value:
            raise ValidationException(
                f"{field_name} 值过大",
                errors={field_name: f"最大值为 {max_value}"}
            )

        return value

    @classmethod
    def validate_decimal(
        cls,
        value: Any,
        field_name: str,
        max_digits: int = 14,
        decimal_places: int = 2,
    ) -> Optional[Decimal]:
        """验证并转换为 Decimal"""
        if value is None:
            return None

        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValidationException(
                f"{field_name} 格式不正确",
                errors={field_name: "请输入有效的数字"}
            )

        # 检查精度
        sign, digits, exponent = decimal_value.as_tuple()
        total_digits = len(digits)
        decimal_digits = -exponent if exponent < 0 else 0
        integer_digits = total_digits - decimal_digits

        if integer_digits + decimal_places > max_digits:
            raise ValidationException(
                f"{field_name} 数值过大",
                errors={field_name: f"整数部分最多 {max_digits - decimal_places} 位"}
            )

        if decimal_digits > decimal_places:
            raise ValidationException(
                f"{field_name} 小数位数过多",
                errors={field_name: f"最多保留 {decimal_places} 位小数"}
            )

        return decimal_value

    @classmethod
    def validate_date(
        cls,
        value: Any,
        field_name: str,
        min_date: Optional[date] = None,
        max_date: Optional[date] = None,
    ) -> Optional[date]:
        """验证日期"""
        if value is None:
            return None

        if isinstance(value, datetime):
            value = value.date()
        elif isinstance(value, str):
            try:
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                raise ValidationException(
                    f"{field_name} 日期格式不正确",
                    errors={field_name: "请使用 YYYY-MM-DD 格式"}
                )
        elif not isinstance(value, date):
            raise ValidationException(
                f"{field_name} 类型不正确",
                errors={field_name: "请提供有效的日期"}
            )

        if min_date and value < min_date:
            raise ValidationException(
                f"{field_name} 日期过早",
                errors={field_name: f"日期不能早于 {min_date}"}
            )

        if max_date and value > max_date:
            raise ValidationException(
                f"{field_name} 日期过晚",
                errors={field_name: f"日期不能晚于 {max_date}"}
            )

        return value

    @classmethod
    def validate_in_choices(
        cls,
        value: Any,
        field_name: str,
        choices: List[Any],
        allow_none: bool = True,
    ) -> Any:
        """验证值是否在选项列表中"""
        if value is None:
            if allow_none:
                return None
            raise ValidationException(
                f"{field_name} 不能为空",
                errors={field_name: "此字段为必填项"}
            )

        if value not in choices:
            raise ValidationException(
                f"{field_name} 值无效",
                errors={field_name: f"有效选项: {', '.join(str(c) for c in choices)}"}
            )

        return value


def validate_model_data(data: dict, rules: dict) -> dict:
    """
    批量验证数据

    Args:
        data: 待验证的数据字典
        rules: 验证规则字典，格式为 {field_name: [(validator_func, kwargs), ...]}

    Returns:
        验证后的数据字典

    Example:
        rules = {
            "phone": [(Validators.validate_phone, {})],
            "amount": [(Validators.validate_decimal, {"max_digits": 10, "decimal_places": 2})],
        }
        validated = validate_model_data(data, rules)
    """
    errors = {}
    validated_data = data.copy()

    for field_name, validators in rules.items():
        value = data.get(field_name)

        for validator_func, kwargs in validators:
            try:
                validated_data[field_name] = validator_func(
                    value, field_name=field_name, **kwargs
                )
            except ValidationException as e:
                errors.update(e.errors)
                break

    if errors:
        raise ValidationException("数据验证失败", errors=errors)

    return validated_data
