"""Module for prompts."""

from __future__ import annotations

"""
诉讼文书生成 Agent 系统提示词

定义 Agent 的角色、能力和工作流程.

Requirements: 1.2
"""
import logging
from typing import cast

logger = logging.getLogger("apps.litigation_ai")


# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = """你是一位专业的诉讼文书生成助手,具有丰富的法律知识和文书写作经验.
你可以帮助律师生成起诉状、答辩状、反诉状、反诉答辩状等诉讼文书.

## 你的能力

你可以使用以下工具来完成任务:

1. **get_case_info** - 获取案件基本信息
   - 包括当事人、案由、标的额、法院信息等
   - 在生成文书前应先调用此工具了解案件情况

2. **get_evidence_list** - 获取案件证据清单
   - 可以按归属过滤(我方/对方)
   - 用于了解案件有哪些证据可用

3. **search_evidence** - 在证据中检索相关内容
   - 使用 RAG 技术检索证据内容
   - 用于查找支持论点的证据

4. **get_recommended_document_types** - 获取推荐的文书类型
   - 根据案件状态和诉讼地位推荐适合的文书类型

5. **generate_draft** - 生成诉讼文书草稿
   - 根据案件信息、诉讼目标和证据生成文书

## 工作流程

1. **了解需求**:首先询问用户想要生成什么类型的文书
2. **获取案件信息**:调用 get_case_info 了解案件基本情况
3. **确认文书类型**:如果用户不确定,调用 get_recommended_document_types 给出建议
4. **收集诉讼目标**:询问用户的诉讼目标和期望结果
5. **检索证据**:根据需要调用 search_evidence 查找相关证据
6. **生成草稿**:调用 generate_draft 生成文书草稿
7. **修改完善**:根据用户反馈进行修改

## 文书类型说明

- **起诉状 (complaint)**:原告向法院提起诉讼的文书
- **答辩状 (defense)**:被告针对原告起诉进行答辩的文书
- **反诉状 (counterclaim)**:被告向原告提起反诉的文书
- **反诉答辩状 (counterclaim_defense)**:原告针对被告反诉进行答辩的文书

## 注意事项

1. 生成的文书应格式规范,符合法律文书要求
2. 事实陈述应清楚,证据引用应准确
3. 法律依据应正确,诉讼请求应明确
4. 使用专业的法律术语,但表达应清晰易懂
5. 如果信息不足,应主动询问用户补充

## 回复风格

- 使用专业但友好的语气
- 回复应简洁明了,避免冗长
- 在需要用户做选择时,给出清晰的选项
- 在生成文书时,先说明将要做什么,再执行
"""


def get_system_prompt(
    document_type: str | None = None,
    custom_instructions: str | None = None,
) -> str:
    """
    获取系统提示词

    支持从数据库加载自定义模板,或使用默认提示词.

    Args:
        document_type: 文书类型(可选,用于加载特定类型的提示词)
        custom_instructions: 自定义指令(可选,追加到提示词末尾)

    Returns:
        系统提示词字符串
    """
    # 尝试从数据库加载
    prompt = _load_prompt_from_db(document_type)

    if not prompt:
        prompt = DEFAULT_SYSTEM_PROMPT

    # 追加自定义指令
    if custom_instructions:
        prompt = f"{prompt}\n\n## 额外指令\n\n{custom_instructions}"

    return prompt


def _load_prompt_from_db(document_type: str | None = None) -> str | None:
    """
    从数据库加载提示词模板

    Args:
        document_type: 文书类型

    Returns:
        提示词字符串,不存在时返回 None
    """
    try:
        from apps.core.models import SystemConfig

        # 尝试加载特定类型的提示词
        if document_type:
            key = f"LITIGATION_AGENT_PROMPT_{document_type.upper()}"
            config = SystemConfig.objects.filter(key=key, is_active=True).first()
            if config and config.value:
                return cast(str, config.value)  # type: ignore[redundant-cast]

        # 加载通用提示词
        config = SystemConfig.objects.filter(
            key="LITIGATION_AGENT_SYSTEM_PROMPT",
            is_active=True,
        ).first()

        if config and config.value:
            return cast(str, config.value)  # type: ignore[redundant-cast]

        return None

    except Exception as e:
        logger.warning(f"从数据库加载提示词失败: {e}")
        return None


def get_document_type_prompt(document_type: str) -> str:
    """
    获取特定文书类型的补充提示词

    Args:
        document_type: 文书类型

    Returns:
        补充提示词
    """
    prompts = {
        "complaint": """
## 起诉状生成要点

1. **诉讼请求**:明确、具体、可执行
2. **事实与理由**:
   - 按时间顺序陈述事实
   - 引用证据支持事实
   - 阐明法律关系
3. **法律依据**:引用相关法律条文
4. **证据清单**:列明证据名称和证明目的
""",
        "defense": """
## 答辩状生成要点

1. **答辩意见**:针对原告诉讼请求逐一答辩
2. **事实反驳**:
   - 指出原告陈述的不实之处
   - 提供我方证据反驳
3. **法律分析**:从法律角度分析原告请求的不当之处
4. **答辩请求**:明确请求驳回原告诉讼请求
""",
        "counterclaim": """
## 反诉状生成要点

1. **反诉请求**:明确反诉的具体请求
2. **反诉事实**:
   - 陈述支持反诉的事实
   - 说明与本诉的关联
3. **反诉理由**:阐明反诉的法律依据
4. **证据支持**:列明支持反诉的证据
""",
        "counterclaim_defense": """
## 反诉答辩状生成要点

1. **答辩意见**:针对被告反诉请求逐一答辩
2. **事实反驳**:指出反诉事实的不实之处
3. **法律分析**:分析反诉请求的不当之处
4. **答辩请求**:请求驳回被告的反诉请求
""",
    }

    return prompts.get(document_type, "")


def build_full_prompt(
    document_type: str | None = None,
    custom_instructions: str | None = None,
) -> str:
    """
    构建完整的系统提示词

    组合基础提示词和文书类型特定提示词.

    Args:
        document_type: 文书类型
        custom_instructions: 自定义指令

    Returns:
        完整的系统提示词
    """
    base_prompt = get_system_prompt(document_type, custom_instructions)

    if document_type:
        type_prompt = get_document_type_prompt(document_type)
        if type_prompt:
            base_prompt = f"{base_prompt}\n{type_prompt}"

    return base_prompt
