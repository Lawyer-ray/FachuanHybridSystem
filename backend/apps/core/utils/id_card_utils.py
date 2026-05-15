"""
身份证号码解析工具类

提供统一的身份证号码解析功能,支持 15 位和 18 位身份证.
"""

import logging
from dataclasses import dataclass
from datetime import date

from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# 校验码权重因子
ID_CARD_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
# 校验码对照表
ID_CARD_CHECK_CODES = ["1", "0", "X", "9", "8", "7", "6", "5", "4", "3", "2"]


@dataclass
class IdCardInfo:
    """身份证信息数据类"""

    birth_date: str | None = None  # 格式:YYYY年MM月DD日
    gender: str | None = None  # 男/女
    age: int | None = None  # 年龄


class IdCardUtils:
    """身份证号码解析工具类"""

    @classmethod
    def parse_id_card_info(cls, id_number: str) -> IdCardInfo:
        """
        解析身份证号码,返回出生日期、性别和年龄

        Args:
            id_number: 身份证号码(15位或18位)

        Returns:
            IdCardInfo: 包含出生日期、性别、年龄的数据类
        """
        if not id_number or len(id_number) < 14:
            return IdCardInfo()

        return IdCardInfo(
            birth_date=cls.extract_birth_date(id_number),
            gender=cls.extract_gender(id_number),
            age=cls.calculate_age(id_number),
        )

    @classmethod
    def extract_birth_date(cls, id_number: str) -> str | None:
        """
        从身份证号码提取出生日期

        Args:
            id_number: 身份证号码

        Returns:
            格式化的出生日期字符串(YYYY年MM月DD日),解析失败返回 None
        """
        if not id_number:
            return None

        try:
            if len(id_number) == 18:
                year = id_number[6:10]
                month = id_number[10:12]
                day = id_number[12:14]
                return f"{year}年{month}月{day}日"
            elif len(id_number) == 15:
                year = "19" + id_number[6:8]
                month = id_number[8:10]
                day = id_number[10:12]
                return f"{year}年{month}月{day}日"
        except (ValueError, IndexError) as e:
            logger.warning(f"解析身份证出生日期失败: {e}")

        return None

    @classmethod
    def extract_gender(cls, id_number: str) -> str | None:
        """
        从身份证号码提取性别

        Args:
            id_number: 身份证号码

        Returns:
            性别字符串(男/女),解析失败返回 None
        """
        if not id_number or len(id_number) < 14:
            return None

        try:
            # 18位身份证:倒数第二位;15位身份证:最后一位
            gender_digit = int(id_number[-2]) if len(id_number) == 18 else int(id_number[-1])
            return "男" if gender_digit % 2 == 1 else "女"
        except (ValueError, IndexError) as e:
            logger.warning(f"解析身份证性别失败: {e}")

        return None

    @classmethod
    def calculate_age(cls, id_number: str) -> int | None:
        """
        从身份证号码计算年龄

        Args:
            id_number: 身份证号码

        Returns:
            年龄(整数),解析失败返回 None
        """
        if not id_number:
            return None

        try:
            if len(id_number) == 18:
                birth_year = int(id_number[6:10])
                birth_month = int(id_number[10:12])
                birth_day = int(id_number[12:14])
            elif len(id_number) == 15:
                birth_year = 1900 + int(id_number[6:8])
                birth_month = int(id_number[8:10])
                birth_day = int(id_number[10:12])
            else:
                return None

            today = date.today()
            age = today.year - birth_year

            # 如果还没过生日,年龄减1
            if (today.month, today.day) < (birth_month, birth_day):
                age -= 1

            return age
        except (ValueError, IndexError) as e:
            logger.warning(f"计算年龄失败: {e}")

        return None

    @classmethod
    def validate_id_card(cls, id_number: str) -> dict[str, str | bool]:
        """
        校验身份证号码是否合法

        校验规则:
        1. 18位身份证:
           - 前17位必须为数字,第18位可以是数字或X(大小写不敏感)
           - 前6位为地区码(简单校验前两位是否为有效省份代码: 11-65)
           - 7-14位为出生日期,需要验证日期是否有效
           - 第18位为校验码,根据前17位通过特定算法计算

        2. 15位身份证(旧版):
           - 全部为数字
           - 前6位为地区码
           - 7-12位为出生日期(YYMMDD),需要验证日期是否有效

        Args:
            id_number: 身份证号码

        Returns:
            dict: {"valid": bool, "message": str}
        """
        if not id_number:
            return {"valid": False, "message": str(_("身份证号码不能为空"))}

        id_number = id_number.strip().upper()

        # 长度校验
        if len(id_number) not in (15, 18):
            return {"valid": False, "message": str(_("身份证号码长度应为15位或18位"))}

        # 18位身份证校验
        if len(id_number) == 18:
            return cls._validate_18_digit_id(id_number)

        # 15位身份证校验
        return cls._validate_15_digit_id(id_number)

    @classmethod
    def _validate_18_digit_id(cls, id_number: str) -> dict[str, str | bool]:
        """校验18位身份证号码"""
        # 前17位必须为数字
        if not id_number[:17].isdigit():
            return {"valid": False, "message": str(_("身份证前17位必须为数字"))}

        # 第18位校验
        last_char = id_number[17]
        if not (last_char.isdigit() or last_char == "X"):
            return {"valid": False, "message": str(_("身份证第18位必须为数字或X"))}

        # 地区码校验(前两位: 11-65)
        province_code = int(id_number[:2])
        if province_code < 11 or province_code > 65:
            return {"valid": False, "message": str(_("身份证地区码无效"))}

        # 出生日期校验
        birth_date_str = id_number[6:14]
        if not cls._validate_birth_date(birth_date_str, is_18_digit=True):
            return {"valid": False, "message": str(_("身份证出生日期无效"))}

        # 校验码计算
        check_sum = 0
        for i in range(17):
            check_sum += int(id_number[i]) * ID_CARD_WEIGHTS[i]

        check_code = ID_CARD_CHECK_CODES[check_sum % 11]

        if id_number[17] != check_code:
            return {"valid": False, "message": str(_("身份证校验码错误，正确校验码应为 %(code)s")) % {"code": check_code}}

        return {"valid": True, "message": str(_("身份证号码格式正确"))}

    @classmethod
    def _validate_15_digit_id(cls, id_number: str) -> dict[str, str | bool]:
        """校验15位身份证号码"""
        # 全部为数字
        if not id_number.isdigit():
            return {"valid": False, "message": str(_("15位身份证必须全部为数字"))}

        # 地区码校验(前两位: 11-65)
        province_code = int(id_number[:2])
        if province_code < 11 or province_code > 65:
            return {"valid": False, "message": str(_("身份证地区码无效"))}

        # 出生日期校验(YYMMDD, 默认19XX年)
        birth_date_str = "19" + id_number[6:12]
        if not cls._validate_birth_date(birth_date_str, is_18_digit=True):
            return {"valid": False, "message": str(_("身份证出生日期无效"))}

        return {"valid": True, "message": str(_("身份证号码格式正确"))}

    @classmethod
    def _validate_birth_date(cls, date_str: str, *, is_18_digit: bool) -> bool:
        """
        校验出生日期是否有效

        Args:
            date_str: 日期字符串(YYYYMMDD格式)
            is_18_digit: 是否为18位身份证格式

        Returns:
            bool: 日期是否有效
        """
        if len(date_str) != 8:
            return False

        try:
            year = int(date_str[:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])

            # 基本范围校验
            if month < 1 or month > 12:
                return False
            if day < 1 or day > 31:
                return False

            # 年份范围校验
            current_year = date.today().year
            if year < 1900 or year > current_year:
                return False

            # 具体日期校验
            date(year, month, day)
            return True
        except (ValueError, TypeError):
            return False
