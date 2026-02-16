"""
身份证号码解析工具类

提供统一的身份证号码解析功能,支持 15 位和 18 位身份证.
"""

import logging
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger(__name__)


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
