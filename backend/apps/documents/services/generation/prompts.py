"""
Prompt 模板管理

使用 LangChain ChatPromptTemplate 管理法律文书生成的 Prompt 模板.
"""

import logging
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger("apps.documents.generation")


class PromptTemplateFactory:
    """Prompt 模板工厂"""

    def get_complaint_prompt(self) -> ChatPromptTemplate:
        """
        获取起诉状 Prompt 模板

        优先从数据库加载活跃版本,如果不存在则使用默认模板.
        模板已集成 JsonOutputParser 的格式说明.

        Returns:
            ChatPromptTemplate: 起诉状 Prompt 模板(包含 format_instructions)
        """
        # 导入 Pydantic 模型
        from .outputs import ComplaintOutput

        # 创建 JsonOutputParser
        parser = JsonOutputParser(pydantic_object=ComplaintOutput)

        # 优先从数据库加载
        db_template = self._load_from_database("complaint")
        if db_template:
            logger.info("使用数据库中的起诉状 Prompt 模板")
            prompt = ChatPromptTemplate.from_template(db_template)
            # 注入格式说明
            return prompt.partial(format_instructions=parser.get_format_instructions())

        # 回退到默认模板
        logger.warning("Prompt 版本不存在,使用默认起诉状模板", extra={"prompt_name": "complaint"})
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "你是一位专业的法律文书撰写助手,擅长撰写各类诉讼文书.请根据提供的信息生成规范的起诉状."),
                (
                    "human",
                    """请根据以下信息生成起诉状:

案由:{cause_of_action}
原告:{plaintiff}
被告:{defendant}
诉讼请求:{litigation_request}
事实与理由:{facts_and_reasons}

请以 JSON 格式返回,包含以下字段:
- title: 标题
- parties: 当事人信息列表,每个包含 name(姓名)、role(角色)、id_number(身份证号)、address(地址)
- litigation_request: 诉讼请求
- facts_and_reasons: 事实与理由
- evidence: 证据列表

{format_instructions}
""",
                ),
            ]
        )
        # 注入格式说明
        return prompt.partial(format_instructions=parser.get_format_instructions())

    def get_defense_prompt(self) -> ChatPromptTemplate:
        """
        获取答辩状 Prompt 模板

        优先从数据库加载活跃版本,如果不存在则使用默认模板.
        模板已集成 JsonOutputParser 的格式说明.

        Returns:
            ChatPromptTemplate: 答辩状 Prompt 模板(包含 format_instructions)
        """
        # 导入 Pydantic 模型
        from .outputs import DefenseOutput

        # 创建 JsonOutputParser
        parser = JsonOutputParser(pydantic_object=DefenseOutput)

        # 优先从数据库加载
        db_template = self._load_from_database("defense")
        if db_template:
            logger.info("使用数据库中的答辩状 Prompt 模板")
            prompt = ChatPromptTemplate.from_template(db_template)
            # 注入格式说明
            return prompt.partial(format_instructions=parser.get_format_instructions())

        # 回退到默认模板
        logger.warning("Prompt 版本不存在,使用默认答辩状模板", extra={"prompt_name": "defense"})
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "你是一位专业的法律文书撰写助手,擅长撰写各类诉讼文书.请根据提供的信息生成规范的答辩状."),
                (
                    "human",
                    """请根据以下信息生成答辩状:

案由:{cause_of_action}
原告:{plaintiff}
被告:{defendant}
答辩意见:{defense_opinion}
答辩理由:{defense_reasons}

请以 JSON 格式返回,包含以下字段:
- title: 标题
- parties: 当事人信息列表,每个包含 name(姓名)、role(角色)、id_number(身份证号)、address(地址)
- defense_opinion: 答辩意见
- defense_reasons: 答辩理由
- evidence: 证据列表

{format_instructions}
""",
                ),
            ]
        )
        # 注入格式说明
        return prompt.partial(format_instructions=parser.get_format_instructions())

    def _load_from_database(self, name: str) -> Any:
        """
        从数据库加载活跃的 Prompt 模板

        Args:
            name: Prompt 名称(如 "complaint", "defense")

        Returns:
            模板字符串,如果不存在则返回 None
        """
        try:
            # 延迟导入避免循环依赖
            from apps.documents.services.prompt_version_service import PromptVersionService

            service = PromptVersionService()
            return service.get_active_template(name)
        except ImportError:
            # PromptVersionService 还未实现时返回 None
            logger.debug("PromptVersionService 未实现,使用默认模板")
            return None
        except Exception:
            logger.exception("load_prompt_from_database_failed", extra={"prompt_name": name})
            raise
