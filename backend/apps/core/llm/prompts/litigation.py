"""
诉状生成 Prompt 模板

定义用于生成诉状内容(诉讼请求和事实与理由)的 Prompt 模板.

Requirements: 4.1, 4.2
"""

from .base import CodePromptTemplate, PromptManager

LITIGATION_PROMPT_TEMPLATE = CodePromptTemplate(
    name="litigation_content",
    template="""你是一位专业的中国法律文书撰写助手,精通各类民事、商事诉讼文书的起草.请根据以下案件信息生成诉状内容.

## 案件信息

- 案件类型:{case_type}
- 案由:{cause_of_action}
- 原告信息:{plaintiff_info}
- 被告信息:{defendant_info}
- 案件事实:{facts}
- 诉讼标的金额:{target_amount}
- 诉状类型:{litigation_type}

## 输出要求

请生成以下内容,严格使用 JSON 格式输出:

```json
{{
    "litigation_request": "诉讼请求内容",
    "facts_and_reasons": "事实与理由内容"
}}
```

## 撰写规范

### 诉讼请求(litigation_request)
1. 按序号列出各项请求,格式如"一、..."、"二、..."
2. 请求应具体、明确、可执行
3. 涉及金额的请求应明确具体数额及计算方式
4. 最后一项通常为"本案诉讼费用由被告承担"

### 事实与理由(facts_and_reasons)
1. 先陈述案件事实,按时间顺序清晰叙述
2. 再阐述法律依据,引用相关法律条文
3. 最后进行法律分析,论证诉讼请求的合理性
4. 语言应规范、专业、逻辑清晰
5. 事实部分应客观陈述,避免主观评价
6. 理由部分应论证充分,法律适用准确

请确保输出的 JSON 格式正确,可被直接解析.""",
    description="诉状内容生成模板,用于生成诉讼请求和事实与理由",
    variables=[
        "case_type",
        "cause_of_action",
        "plaintiff_info",
        "defendant_info",
        "facts",
        "target_amount",
        "litigation_type",
    ],
)


# 注册模板到 PromptManager
PromptManager.register(LITIGATION_PROMPT_TEMPLATE)
