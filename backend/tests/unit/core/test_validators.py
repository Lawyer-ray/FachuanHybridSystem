"""
验证器单元测试
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.core.exceptions import ValidationException
from apps.core.validators import Validators, validate_model_data


class ValidatorsTest(TestCase):
    """验证器测试"""

    def test_validate_phone_valid(self):
        """测试有效手机号"""
        self.assertEqual(Validators.validate_phone("13800138000"), "13800138000")
        self.assertEqual(Validators.validate_phone("  13800138000  "), "13800138000")
        # 测试所有有效的手机号前缀
        valid_prefixes = ["13", "14", "15", "16", "17", "18", "19"]
        for prefix in valid_prefixes:
            phone = f"{prefix}012345678"
            self.assertEqual(Validators.validate_phone(phone), phone)

    def test_validate_phone_invalid(self):
        """测试无效手机号"""
        with self.assertRaises(ValidationException):
            Validators.validate_phone("12345678901")  # 不是1开头
        with self.assertRaises(ValidationException):
            Validators.validate_phone("1380013800")  # 10位
        with self.assertRaises(ValidationException):
            Validators.validate_phone("138001380001")  # 12位
        with self.assertRaises(ValidationException):
            Validators.validate_phone("abc")
        with self.assertRaises(ValidationException):
            Validators.validate_phone("12012345678")  # 12开头无效

    def test_validate_phone_none(self):
        """测试空手机号"""
        self.assertIsNone(Validators.validate_phone(None))
        self.assertIsNone(Validators.validate_phone(""))
        self.assertIsNone(Validators.validate_phone("   "))

    def test_validate_email_valid(self):
        """测试有效邮箱"""
        self.assertEqual(Validators.validate_email("test@example.com"), "test@example.com")
        self.assertEqual(Validators.validate_email("TEST@EXAMPLE.COM"), "test@example.com")
        self.assertEqual(Validators.validate_email("user.name@example.com"), "user.name@example.com")
        self.assertEqual(Validators.validate_email("user+tag@example.co.uk"), "user+tag@example.co.uk")

    def test_validate_email_invalid(self):
        """测试无效邮箱"""
        with self.assertRaises(ValidationException):
            Validators.validate_email("invalid")
        with self.assertRaises(ValidationException):
            Validators.validate_email("test@")
        with self.assertRaises(ValidationException):
            Validators.validate_email("@example.com")
        with self.assertRaises(ValidationException):
            Validators.validate_email("test@.com")

    def test_validate_email_none(self):
        """测试空邮箱"""
        self.assertIsNone(Validators.validate_email(None))
        self.assertIsNone(Validators.validate_email(""))

    def test_validate_id_card_valid(self):
        """测试有效身份证号"""
        # 使用一个符合校验规则的测试号码（校验码正确）
        valid_id = "110101199003074514"
        result = Validators.validate_id_card(valid_id)
        self.assertEqual(result, valid_id)

    def test_validate_id_card_invalid_format(self):
        """测试无效身份证格式"""
        with self.assertRaises(ValidationException):
            Validators.validate_id_card("12345678901234567X")
        with self.assertRaises(ValidationException):
            Validators.validate_id_card("11010119900307451")  # 17位
        with self.assertRaises(ValidationException):
            Validators.validate_id_card("210101199003074514")  # 无效地区码

    def test_validate_id_card_invalid_checksum(self):
        """测试身份证校验码错误"""
        with self.assertRaises(ValidationException):
            Validators.validate_id_card("110101199003074515")  # 校验码错误

    def test_validate_id_card_none(self):
        """测试空身份证"""
        self.assertIsNone(Validators.validate_id_card(None))
        self.assertIsNone(Validators.validate_id_card(""))

    def test_validate_social_credit_code_valid(self):
        """测试有效统一社会信用代码"""
        valid_code = "91110000600037341L"
        result = Validators.validate_social_credit_code(valid_code)
        self.assertEqual(result, valid_code)

    def test_validate_social_credit_code_invalid(self):
        """测试无效统一社会信用代码"""
        with self.assertRaises(ValidationException):
            Validators.validate_social_credit_code("12345678901234567")  # 长度不对
        with self.assertRaises(ValidationException):
            Validators.validate_social_credit_code("91110000600037341")  # 17位

    def test_validate_social_credit_code_none(self):
        """测试空统一社会信用代码"""
        self.assertIsNone(Validators.validate_social_credit_code(None))
        self.assertIsNone(Validators.validate_social_credit_code(""))

    def test_validate_required(self):
        """测试必填验证"""
        self.assertEqual(Validators.validate_required("value", "field"), "value")
        self.assertEqual(Validators.validate_required(0, "field"), 0)
        self.assertEqual(Validators.validate_required(False, "field"), False)

        with self.assertRaises(ValidationException):
            Validators.validate_required(None, "field")
        with self.assertRaises(ValidationException):
            Validators.validate_required("", "field")
        with self.assertRaises(ValidationException):
            Validators.validate_required("   ", "field")

    def test_validate_length(self):
        """测试长度验证"""
        self.assertEqual(Validators.validate_length("hello", "field", min_length=3, max_length=10), "hello")
        self.assertEqual(Validators.validate_length("abc", "field", min_length=3), "abc")
        self.assertEqual(Validators.validate_length("hello", "field", max_length=10), "hello")

        with self.assertRaises(ValidationException):
            Validators.validate_length("hi", "field", min_length=3)
        with self.assertRaises(ValidationException):
            Validators.validate_length("hello world", "field", max_length=5)

    def test_validate_length_none(self):
        """测试长度验证空值"""
        self.assertIsNone(Validators.validate_length(None, "field", min_length=3))
        self.assertIsNone(Validators.validate_length("", "field", min_length=3))

    def test_validate_range(self):
        """测试数值范围验证"""
        self.assertEqual(Validators.validate_range(50, "field", min_value=0, max_value=100), 50)
        self.assertEqual(Validators.validate_range(0, "field", min_value=0), 0)
        self.assertEqual(Validators.validate_range(100, "field", max_value=100), 100)
        self.assertEqual(Validators.validate_range(50.5, "field", min_value=0, max_value=100), 50.5)

        with self.assertRaises(ValidationException):
            Validators.validate_range(-1, "field", min_value=0)
        with self.assertRaises(ValidationException):
            Validators.validate_range(101, "field", max_value=100)

    def test_validate_range_none(self):
        """测试数值范围验证空值"""
        self.assertIsNone(Validators.validate_range(None, "field", min_value=0))

    def test_validate_decimal(self):
        """测试 Decimal 验证"""
        result = Validators.validate_decimal("123.45", "amount")
        self.assertEqual(result, Decimal("123.45"))

        result = Validators.validate_decimal(100, "amount")
        self.assertEqual(result, Decimal("100"))

        result = Validators.validate_decimal(Decimal("99.99"), "amount")
        self.assertEqual(result, Decimal("99.99"))

        with self.assertRaises(ValidationException):
            Validators.validate_decimal("invalid", "amount")
        with self.assertRaises(ValidationException):
            Validators.validate_decimal("123.456", "amount", decimal_places=2)  # 小数位数过多

    def test_validate_decimal_none(self):
        """测试 Decimal 验证空值"""
        self.assertIsNone(Validators.validate_decimal(None, "amount"))

    def test_validate_decimal_precision(self):
        """测试 Decimal 精度验证"""
        # 测试整数部分过大
        with self.assertRaises(ValidationException):
            Validators.validate_decimal("123456789012.34", "amount", max_digits=14, decimal_places=2)

    def test_validate_date(self):
        """测试日期验证"""
        result = Validators.validate_date("2024-01-15", "date_field")
        self.assertEqual(result, date(2024, 1, 15))

        result = Validators.validate_date(date(2024, 1, 15), "date_field")
        self.assertEqual(result, date(2024, 1, 15))

        # 测试日期范围
        result = Validators.validate_date(
            "2024-01-15", "date_field", min_date=date(2024, 1, 1), max_date=date(2024, 12, 31)
        )
        self.assertEqual(result, date(2024, 1, 15))

        with self.assertRaises(ValidationException):
            Validators.validate_date("invalid", "date_field")
        with self.assertRaises(ValidationException):
            Validators.validate_date("2024-13-01", "date_field")  # 无效月份
        with self.assertRaises(ValidationException):
            Validators.validate_date("2024-01-15", "date_field", min_date=date(2024, 2, 1))
        with self.assertRaises(ValidationException):
            Validators.validate_date("2024-01-15", "date_field", max_date=date(2024, 1, 1))

    def test_validate_date_none(self):
        """测试日期验证空值"""
        self.assertIsNone(Validators.validate_date(None, "date_field"))

    def test_validate_in_choices(self):
        """测试选项验证"""
        choices = ["a", "b", "c"]
        self.assertEqual(Validators.validate_in_choices("a", "field", choices), "a")
        self.assertIsNone(Validators.validate_in_choices(None, "field", choices))

        with self.assertRaises(ValidationException):
            Validators.validate_in_choices("d", "field", choices)
        with self.assertRaises(ValidationException):
            Validators.validate_in_choices(None, "field", choices, allow_none=False)

    def test_validate_in_choices_numeric(self):
        """测试数字选项验证"""
        choices = [1, 2, 3]
        self.assertEqual(Validators.validate_in_choices(1, "field", choices), 1)
        self.assertEqual(Validators.validate_in_choices(2, "field", choices), 2)

        with self.assertRaises(ValidationException):
            Validators.validate_in_choices(4, "field", choices)


class ValidateModelDataTest(TestCase):
    """批量验证测试"""

    def test_validate_model_data_success(self):
        """测试批量验证成功"""
        data = {
            "phone": "13800138000",
            "amount": "100.50",
        }
        rules = {
            "phone": [(Validators.validate_phone, {})],
            "amount": [(Validators.validate_decimal, {"max_digits": 10, "decimal_places": 2})],
        }

        result = validate_model_data(data, rules)
        self.assertEqual(result["phone"], "13800138000")
        self.assertEqual(result["amount"], Decimal("100.50"))

    def test_validate_model_data_failure(self):
        """测试批量验证失败"""
        data = {
            "phone": "invalid",
            "amount": "100.50",
        }
        rules = {
            "phone": [(Validators.validate_phone, {})],
        }

        with self.assertRaises(ValidationException) as ctx:
            validate_model_data(data, rules)

        self.assertIn("phone", ctx.exception.errors)
