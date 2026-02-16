"""
通用的 Hypothesis 策略
"""
from hypothesis import strategies as st
from decimal import Decimal


@st.composite
def chinese_text(draw, min_size=1, max_size=100):
    """
    生成中文文本
    
    Args:
        min_size: 最小长度
        max_size: 最大长度
        
    Returns:
        str: 中文文本
    """
    # 常用汉字范围：U+4E00 到 U+9FFF
    chinese_chars = st.characters(
        min_codepoint=0x4E00,
        max_codepoint=0x9FFF
    )
    
    return draw(st.text(
        alphabet=chinese_chars,
        min_size=min_size,
        max_size=max_size
    ))


@st.composite
def phone_number(draw):
    """
    生成手机号码
    
    Returns:
        str: 11位手机号码
    """
    # 中国手机号码：13x, 14x, 15x, 16x, 17x, 18x, 19x
    prefix = draw(st.sampled_from(['13', '14', '15', '16', '17', '18', '19']))
    suffix = draw(st.integers(min_value=0, max_value=999999999))
    return f"{prefix}{suffix:09d}"


@st.composite
def id_card_number(draw):
    """
    生成身份证号码（18位）
    
    Returns:
        str: 18位身份证号码
    """
    # 地区码（前6位）
    area_code = draw(st.integers(min_value=110000, max_value=659999))
    
    # 出生日期（8位）
    year = draw(st.integers(min_value=1950, max_value=2010))
    month = draw(st.integers(min_value=1, max_value=12))
    day = draw(st.integers(min_value=1, max_value=28))  # 简化处理
    
    # 顺序码（3位）
    sequence = draw(st.integers(min_value=0, max_value=999))
    
    # 校验码（1位，简化为随机数字）
    check_digit = draw(st.integers(min_value=0, max_value=9))
    
    return f"{area_code}{year:04d}{month:02d}{day:02d}{sequence:03d}{check_digit}"


@st.composite
def case_number(draw):
    """
    生成案号
    
    Returns:
        str: 案号，格式如 "（2024）粤01民初12345号"
    """
    year = draw(st.integers(min_value=2020, max_value=2025))
    province = draw(st.sampled_from(['粤', '京', '沪', '津', '渝']))
    court_code = draw(st.integers(min_value=1, max_value=99))
    case_type = draw(st.sampled_from(['民初', '民终', '刑初', '刑终', '行初']))
    number = draw(st.integers(min_value=1, max_value=99999))
    
    return f"（{year}）{province}{court_code:02d}{case_type}{number}号"


@st.composite
def decimal_amount(draw, min_value=0, max_value=1000000, decimal_places=2):
    """
    生成金额（Decimal）
    
    Args:
        min_value: 最小值
        max_value: 最大值
        decimal_places: 小数位数
        
    Returns:
        Decimal: 金额
    """
    # 生成整数部分
    integer_part = draw(st.integers(min_value=min_value, max_value=max_value))
    
    # 生成小数部分
    decimal_part = draw(st.integers(min_value=0, max_value=10**decimal_places - 1))
    
    # 组合成 Decimal
    value = Decimal(f"{integer_part}.{decimal_part:0{decimal_places}d}")
    
    return value
