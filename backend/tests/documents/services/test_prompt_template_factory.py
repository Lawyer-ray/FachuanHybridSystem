"""
测试 PromptTemplateFactory

验证 Prompt 模板的创建和变量替换功能。
"""

import pytest
from langchain_core.prompts import ChatPromptTemplate


class TestPromptTemplateFactory:
    """测试 PromptTemplateFactory 类"""

    def test_get_complaint_prompt_returns_template(self):
        """测试获取起诉状 Prompt 模板"""
        from apps.documents.services.generation.prompts import PromptTemplateFactory

        prompt = PromptTemplateFactory().get_complaint_prompt()

        assert prompt is not None
        assert isinstance(prompt, ChatPromptTemplate)

    def test_complaint_prompt_has_required_variables(self):
        """测试起诉状模板包含所有必需的变量"""
        from apps.documents.services.generation.prompts import PromptTemplateFactory

        prompt = PromptTemplateFactory().get_complaint_prompt()

        # 获取模板中的变量
        input_variables = prompt.input_variables

        # 验证包含所有必需的变量
        required_vars = ["cause_of_action", "plaintiff", "defendant", "litigation_request", "facts_and_reasons"]

        for var in required_vars:
            assert var in input_variables, f"模板缺少必需变量: {var}"

    def test_complaint_prompt_format_with_values(self):
        """测试起诉状模板能够正确格式化变量"""
        from apps.documents.services.generation.prompts import PromptTemplateFactory

        prompt = PromptTemplateFactory().get_complaint_prompt()

        # 准备测试数据
        test_data = {
            "cause_of_action": "合同纠纷",
            "plaintiff": "张三",
            "defendant": "李四",
            "litigation_request": "请求判令被告支付货款10万元",
            "facts_and_reasons": "原告与被告签订买卖合同...",
            "format_instructions": "",  # 空的格式说明
        }

        # 格式化模板
        messages = prompt.format_messages(**test_data)

        # 验证消息数量（应该有 system 和 human 两条消息）
        assert len(messages) == 2

        # 验证第一条是 system 消息
        assert messages[0].type == "system"
        assert "法律文书" in messages[0].content

        # 验证第二条是 human 消息，包含所有变量值
        assert messages[1].type == "human"
        human_content = messages[1].content

        assert "合同纠纷" in human_content
        assert "张三" in human_content
        assert "李四" in human_content
        assert "请求判令被告支付货款10万元" in human_content
        assert "原告与被告签订买卖合同" in human_content

    def test_complaint_prompt_with_empty_values(self):
        """测试起诉状模板处理空值的边缘情况"""
        from apps.documents.services.generation.prompts import PromptTemplateFactory

        prompt = PromptTemplateFactory().get_complaint_prompt()

        # 使用空字符串
        test_data = {
            "cause_of_action": "",
            "plaintiff": "",
            "defendant": "",
            "litigation_request": "",
            "facts_and_reasons": "",
            "format_instructions": "",
        }

        # 应该能够成功格式化，不抛出异常
        messages = prompt.format_messages(**test_data)

        assert len(messages) == 2
        assert messages[0].type == "system"
        assert messages[1].type == "human"

    def test_get_defense_prompt_returns_template(self):
        """测试获取答辩状 Prompt 模板"""
        from apps.documents.services.generation.prompts import PromptTemplateFactory

        prompt = PromptTemplateFactory().get_defense_prompt()

        assert prompt is not None
        assert isinstance(prompt, ChatPromptTemplate)

    def test_defense_prompt_has_required_variables(self):
        """测试答辩状模板包含所有必需的变量"""
        from apps.documents.services.generation.prompts import PromptTemplateFactory

        prompt = PromptTemplateFactory().get_defense_prompt()

        # 获取模板中的变量
        input_variables = prompt.input_variables

        # 验证包含所有必需的变量
        required_vars = ["cause_of_action", "plaintiff", "defendant", "defense_opinion", "defense_reasons"]

        for var in required_vars:
            assert var in input_variables, f"模板缺少必需变量: {var}"

    def test_defense_prompt_format_with_values(self):
        """测试答辩状模板能够正确格式化变量"""
        from apps.documents.services.generation.prompts import PromptTemplateFactory

        prompt = PromptTemplateFactory().get_defense_prompt()

        # 准备测试数据
        test_data = {
            "cause_of_action": "合同纠纷",
            "plaintiff": "张三",
            "defendant": "李四",
            "defense_opinion": "原告的诉讼请求缺乏事实和法律依据，应予驳回",
            "defense_reasons": "一、原告主张的合同关系不成立...",
            "format_instructions": "",  # 空的格式说明
        }

        # 格式化模板
        messages = prompt.format_messages(**test_data)

        # 验证消息数量（应该有 system 和 human 两条消息）
        assert len(messages) == 2

        # 验证第一条是 system 消息
        assert messages[0].type == "system"
        assert "法律文书" in messages[0].content

        # 验证第二条是 human 消息，包含所有变量值
        assert messages[1].type == "human"
        human_content = messages[1].content

        assert "合同纠纷" in human_content
        assert "张三" in human_content
        assert "李四" in human_content
        assert "原告的诉讼请求缺乏事实和法律依据，应予驳回" in human_content
        assert "一、原告主张的合同关系不成立" in human_content

    def test_defense_prompt_with_empty_values(self):
        """测试答辩状模板处理空值的边缘情况"""
        from apps.documents.services.generation.prompts import PromptTemplateFactory

        prompt = PromptTemplateFactory().get_defense_prompt()

        # 使用空字符串
        test_data = {
            "cause_of_action": "",
            "plaintiff": "",
            "defendant": "",
            "defense_opinion": "",
            "defense_reasons": "",
            "format_instructions": "",
        }

        # 应该能够成功格式化，不抛出异常
        messages = prompt.format_messages(**test_data)

        assert len(messages) == 2
        assert messages[0].type == "system"
        assert messages[1].type == "human"
