"""
DocumentRenamer 属性测试
使用 Hypothesis 进行基于属性的测试
"""
import re
import pytest
from datetime import date
from hypothesis import given, strategies as st, settings

from apps.automation.services.sms.document_renamer import DocumentRenamer


# 定义策略
@st.composite
def valid_title_strategy(draw):
    """生成有效文书标题策略"""
    # 常见的文书类型
    common_titles = [
        "判决书", "裁定书", "调解书", "决定书", "传票", "通知书", "支付令",
        "财产保全裁定书", "执行通知书", "应诉通知书", "举证通知书", 
        "执行裁定书", "仲裁裁决书", "开庭传票"
    ]
    
    title_type = draw(st.sampled_from(['common', 'custom', 'empty']))
    
    if title_type == 'common':
        return draw(st.sampled_from(common_titles))
    elif title_type == 'custom':
        # 生成自定义标题（1-20个字符）
        return draw(st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd', 'Lo'),  # 字母、数字、汉字
                blacklist_characters='<>:"|?*\\/.'  # 排除文件名非法字符
            )
        ))
    else:
        return ""


@st.composite
def valid_case_name_strategy(draw):
    """生成有效案件名称策略"""
    case_name_type = draw(st.sampled_from(['normal', 'long', 'with_special_chars', 'empty']))
    
    if case_name_type == 'normal':
        # 正常案件名称（10-30个字符）
        return draw(st.text(
            min_size=10,
            max_size=30,
            alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd', 'Lo'),
                blacklist_characters='<>:"|?*\\/.'
            )
        ))
    elif case_name_type == 'long':
        # 长案件名称（超过30个字符）
        return draw(st.text(
            min_size=31,
            max_size=100,
            alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd', 'Lo'),
                blacklist_characters='<>:"|?*\\/.'
            )
        ))
    elif case_name_type == 'with_special_chars':
        # 包含特殊字符的案件名称
        base_name = draw(st.text(
            min_size=5,
            max_size=20,
            alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd', 'Lo')
            )
        ))
        # 添加一些可能出现的特殊字符
        special_chars = draw(st.text(
            min_size=1,
            max_size=5,
            alphabet='<>:"|?*\\/()[]{}，。、；：""''！？'
        ))
        return base_name + special_chars
    else:
        return ""


@st.composite
def valid_date_strategy(draw):
    """生成有效日期策略"""
    # 生成合理的日期范围（2000-2030年）
    year = draw(st.integers(min_value=2000, max_value=2030))
    month = draw(st.integers(min_value=1, max_value=12))
    
    # 根据月份确定天数范围
    if month in [1, 3, 5, 7, 8, 10, 12]:
        max_day = 31
    elif month in [4, 6, 9, 11]:
        max_day = 30
    else:  # 2月
        # 简单处理，不考虑闰年
        max_day = 28
    
    day = draw(st.integers(min_value=1, max_value=max_day))
    
    return date(year, month, day)


@pytest.mark.django_db
class TestDocumentRenamerProperties:
    """DocumentRenamer 属性测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.renamer = DocumentRenamer()
    
    @settings(max_examples=100, deadline=None)
    @given(
        title=valid_title_strategy(),
        case_name=valid_case_name_strategy(),
        received_date=valid_date_strategy()
    )
    def test_property_7_filename_format_correctness(self, title, case_name, received_date):
        """
        属性 7: 文件名格式正确性
        
        **Feature: court-sms-processing, Property 7: 文件名格式正确性**
        **Validates: Requirements 4.3**
        
        对于任何有效的主标题、案件名称和日期，generate_filename() 生成的文件名
        应符合格式 `{主标题}（{案件名称}）_{YYYYMMDD}收.pdf`
        """
        # 执行文件名生成
        filename = self.renamer.generate_filename(title, case_name, received_date)
        
        # 验证：返回结果是字符串
        assert isinstance(filename, str), f"文件名必须是字符串类型: {type(filename)}"
        
        # 验证：文件名不为空
        assert len(filename) > 0, "文件名不应为空"
        
        # 验证：文件名以 .pdf 结尾
        assert filename.endswith('.pdf'), f"文件名应以 .pdf 结尾: {filename}"
        
        # 验证：文件名包含 "收" 字符
        assert '收' in filename, f"文件名应包含'收'字符: {filename}"
        
        # 验证：文件名包含日期格式 YYYYMMDD
        date_pattern = r'\d{8}'
        assert re.search(date_pattern, filename), f"文件名应包含8位数字日期: {filename}"
        
        # 验证：日期格式正确
        expected_date_str = received_date.strftime("%Y%m%d")
        assert expected_date_str in filename, f"文件名应包含正确的日期 {expected_date_str}: {filename}"
        
        # 验证：基本格式结构
        # 格式：{主标题}（{案件名称}）_{YYYYMMDD}收.pdf
        basic_pattern = r'^.+（.+）_\d{8}收\.pdf$'
        assert re.match(basic_pattern, filename), f"文件名应符合基本格式: {filename}"
        
        # 验证：中文括号的使用
        assert '（' in filename, f"文件名应包含中文左括号: {filename}"
        assert '）' in filename, f"文件名应包含中文右括号: {filename}"
        
        # 验证：不包含英文括号
        assert '(' not in filename, f"文件名不应包含英文左括号: {filename}"
        assert ')' not in filename, f"文件名不应包含英文右括号: {filename}"
        
        # 验证：下划线的正确使用
        assert '_' in filename, f"文件名应包含下划线分隔符: {filename}"
        
        # 验证：文件名中不包含非法字符
        illegal_chars = r'[<>:"|?*\\/]'
        assert not re.search(illegal_chars, filename), f"文件名不应包含非法字符: {filename}"
        
        # 验证：文件名长度合理
        assert len(filename) <= 255, f"文件名长度不应超过255字符: {len(filename)}"
        
        # 验证：处理空值的默认行为
        if not title.strip():
            assert filename.startswith('司法文书'), f"空标题应使用默认值'司法文书': {filename}"
        
        if not case_name.strip():
            assert '未知案件' in filename, f"空案件名称应使用默认值'未知案件': {filename}"
        
        # 验证：长度限制处理
        # 提取文件名各部分进行验证
        # 格式：{主标题}（{案件名称}）_{YYYYMMDD}收.pdf
        match = re.match(r'^(.+)（(.+)）_(\d{8})收\.pdf$', filename)
        assert match, f"文件名应能被正确解析: {filename}"
        
        actual_title, actual_case_name, actual_date = match.groups()
        
        # 验证：标题长度限制（最多20个字符）
        assert len(actual_title) <= 20, f"标题部分长度不应超过20字符: {len(actual_title)}, {actual_title}"
        
        # 验证：案件名称长度限制（最多30个字符）
        assert len(actual_case_name) <= 30, f"案件名称部分长度不应超过30字符: {len(actual_case_name)}, {actual_case_name}"
        
        # 验证：日期部分正确
        assert actual_date == expected_date_str, f"日期部分应正确: {actual_date} != {expected_date_str}"
        
        # 验证：如果原始标题不为空，实际标题应该包含原始标题的内容（可能被截断）
        if title.strip():
            # 清理后的标题应该是原始标题的前缀或包含原始标题的主要内容
            cleaned_original_title = self.renamer._sanitize_filename_part(title)
            if cleaned_original_title:
                # 如果原始标题很长，实际标题应该是截断版本
                if len(cleaned_original_title) > 20:
                    expected_truncated = cleaned_original_title[:20]
                    assert actual_title == expected_truncated, \
                        f"长标题应被正确截断: {actual_title} != {expected_truncated}"
                else:
                    assert actual_title == cleaned_original_title, \
                        f"短标题应保持不变: {actual_title} != {cleaned_original_title}"
        
        # 验证：如果原始案件名称不为空，实际案件名称应该包含原始案件名称的内容
        if case_name.strip():
            cleaned_original_case_name = self.renamer._sanitize_filename_part(case_name)
            if cleaned_original_case_name:
                if len(cleaned_original_case_name) > 30:
                    expected_truncated = cleaned_original_case_name[:30]
                    assert actual_case_name == expected_truncated, \
                        f"长案件名称应被正确截断: {actual_case_name} != {expected_truncated}"
                else:
                    assert actual_case_name == cleaned_original_case_name, \
                        f"短案件名称应保持不变: {actual_case_name} != {cleaned_original_case_name}"
        
        # 验证：特殊字符处理
        # 验证实际的标题和案件名称不包含非法字符
        assert not re.search(illegal_chars, actual_title), \
            f"标题部分不应包含非法字符: {actual_title}"
        assert not re.search(illegal_chars, actual_case_name), \
            f"案件名称部分不应包含非法字符: {actual_case_name}"
        
        # 验证：控制字符处理
        control_chars = r'[\x00-\x1f\x7f]'
        assert not re.search(control_chars, filename), \
            f"文件名不应包含控制字符: {repr(filename)}"
        
        # 验证：首尾空格和点号处理
        assert not actual_title.startswith(' '), f"标题不应以空格开头: '{actual_title}'"
        assert not actual_title.endswith(' '), f"标题不应以空格结尾: '{actual_title}'"
        assert not actual_title.startswith('.'), f"标题不应以点号开头: '{actual_title}'"
        assert not actual_title.endswith('.'), f"标题不应以点号结尾: '{actual_title}'"
        
        assert not actual_case_name.startswith(' '), f"案件名称不应以空格开头: '{actual_case_name}'"
        assert not actual_case_name.endswith(' '), f"案件名称不应以空格结尾: '{actual_case_name}'"
        assert not actual_case_name.startswith('.'), f"案件名称不应以点号开头: '{actual_case_name}'"
        assert not actual_case_name.endswith('.'), f"案件名称不应以点号结尾: '{actual_case_name}'"
        
        # 验证：文件名的唯一性和可重现性
        # 相同输入应产生相同输出
        filename2 = self.renamer.generate_filename(title, case_name, received_date)
        assert filename == filename2, f"相同输入应产生相同文件名: {filename} != {filename2}"
        
        # 验证：文件名的可用性
        # 生成的文件名应该可以在文件系统中使用
        try:
            filename.encode('utf-8')
        except UnicodeEncodeError:
            pytest.fail(f"文件名应该可以正确编码为UTF-8: {filename}")
        
        # 验证：Windows文件名兼容性
        # 检查Windows保留名称
        windows_reserved_names = [
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        ]
        
        filename_without_ext = filename.rsplit('.', 1)[0]
        assert filename_without_ext.upper() not in windows_reserved_names, \
            f"文件名不应使用Windows保留名称: {filename}"
        
        # 验证：格式的完整性
        # 确保所有必需的组件都存在
        components = {
            'title': actual_title,
            'case_name': actual_case_name,
            'date': actual_date,
            'suffix': '收',
            'extension': '.pdf'
        }
        
        for component_name, component_value in components.items():
            if component_name == 'extension':
                assert filename.endswith(component_value), \
                    f"文件名应包含{component_name}: {component_value}"
            else:
                assert str(component_value) in filename, \
                    f"文件名应包含{component_name}: {component_value}"
        
        # 验证：日期格式的严格性
        # 日期应该是8位数字，格式为YYYYMMDD
        assert len(actual_date) == 8, f"日期应该是8位数字: {actual_date}"
        assert actual_date.isdigit(), f"日期应该全部是数字: {actual_date}"
        
        # 验证日期的合理性
        try:
            parsed_year = int(actual_date[:4])
            parsed_month = int(actual_date[4:6])
            parsed_day = int(actual_date[6:8])
            
            assert 1000 <= parsed_year <= 9999, f"年份应该是4位数: {parsed_year}"
            assert 1 <= parsed_month <= 12, f"月份应该在1-12之间: {parsed_month}"
            assert 1 <= parsed_day <= 31, f"日期应该在1-31之间: {parsed_day}"
            
            # 验证日期与输入的一致性
            assert parsed_year == received_date.year, f"年份应该匹配: {parsed_year} != {received_date.year}"
            assert parsed_month == received_date.month, f"月份应该匹配: {parsed_month} != {received_date.month}"
            assert parsed_day == received_date.day, f"日期应该匹配: {parsed_day} != {received_date.day}"
            
        except ValueError as e:
            pytest.fail(f"日期格式应该可以正确解析: {actual_date}, 错误: {e}")
        
        # 验证：边界情况处理
        # 测试极端输入的处理
        if len(title) == 0 and len(case_name) == 0:
            # 两个都为空的情况
            assert '司法文书' in filename, "空输入应使用默认标题"
            assert '未知案件' in filename, "空输入应使用默认案件名称"
        
        # 验证：格式字符串的稳定性
        # 确保格式符合预期的模式
        expected_pattern = rf'^.+（.+）_{expected_date_str}收\.pdf$'
        assert re.match(expected_pattern, filename), \
            f"文件名应符合预期格式模式: {filename}"
        
        # 验证：中文字符处理
        # 确保中文字符被正确处理
        chinese_char_pattern = r'[\u4e00-\u9fa5]'
        if re.search(chinese_char_pattern, title) or re.search(chinese_char_pattern, case_name):
            # 如果输入包含中文字符，输出也应该正确包含中文字符
            assert re.search(chinese_char_pattern, filename), \
                f"包含中文输入时，文件名也应包含中文字符: {filename}"
        
        # 验证：数字和字母处理
        # 确保数字和字母被正确保留
        if re.search(r'[a-zA-Z0-9]', title):
            # 输入包含字母或数字时，应该被保留（除非被截断）
            pass  # 由于可能被截断或清理，我们不强制要求
        
        # 验证：文件名的可读性
        # 生成的文件名应该是人类可读的
        assert len(actual_title) > 0, "标题部分不应为空"
        assert len(actual_case_name) > 0, "案件名称部分不应为空"
        
        # 验证：格式的一致性
        # 确保格式在不同输入下保持一致
        # 所有生成的文件名都应该遵循相同的格式规则
        format_elements = [
            ('title_part', actual_title),
            ('left_paren', '（'),
            ('case_part', actual_case_name),
            ('right_paren', '）'),
            ('underscore', '_'),
            ('date_part', actual_date),
            ('suffix', '收'),
            ('extension', '.pdf')
        ]
        
        # 重新构建文件名并验证
        reconstructed = ''.join([element[1] for element in format_elements])
        assert filename == reconstructed, \
            f"文件名应该可以按格式重新构建: {filename} != {reconstructed}"