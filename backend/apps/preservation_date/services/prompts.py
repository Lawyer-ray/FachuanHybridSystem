"""
财产保全日期识别提示词模块

设计大模型提示词,用于从法院文书中识别财产保全措施并提取相关信息.
要求大模型返回结构化 JSON 格式的结果.

Requirements: 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4
"""

# 财产保全日期提取主提示词
PRESERVATION_DATE_EXTRACTION_PROMPT = """
你是一名专业的法律文书分析助手.请从以下法院文书中识别【所有】财产保全措施.

## 任务要求

1. 识别文书中的所有查封、冻结、扣押、轮候查封、轮候冻结措施
2. 每种措施类型单独输出一条记录
3. 不要遗漏任何一项保全措施

## 输出格式

```json
{{
  "measures": [
    {{
      "measure_type": "查封/冻结/扣押/轮候查封/轮候冻结",
      "property_description": "被保全财产的描述",
      "duration": "期限如'一年'、'三年'",
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "is_pending": true/false,
      "pending_note": "备注",
      "raw_text": "原始文本"
    }}
  ]
}}
```

## 核心规则

### 1. 轮候 vs 正式措施的区分
- 含"轮候"字样 → measure_type 填"轮候查封"或"轮候冻结",is_pending=true
- 不含"轮候"字样 → measure_type 填"查封"、"冻结"或"扣押",is_pending=false

### 2. 轮候措施的日期处理(法律依据:最高法院查封冻结规定第28条)
轮候状态下期限尚未起算,因此:
- duration、start_date、end_date 都填 null
- pending_note 填"轮候状态,期限自转为正式查封/冻结之日起算"

### 3. 复合句拆分(重要)
同一句话中如果同时出现"轮候冻结...冻结...",必须拆分成两条记录:

原文示例:
"轮候冻结A账户、B账户、冻结C账户、D账户,冻结期限一年,自2025年2月11日起至2026年2月10日止"

正确输出(2条记录):
- 记录1:轮候冻结 A账户、B账户,is_pending=true,end_date=null
- 记录2:冻结 C账户、D账户,is_pending=false,end_date=2026-02-10

期限只归属于正式冻结,不归属于轮候冻结.

## 开始识别

以下是法院文书内容:
{text}

/no_think"""

# 保全措施类型列表(用于验证和提示)
PRESERVATION_MEASURE_TYPES = [
    "查封",
    "冻结",
    "扣押",
    "轮候查封",
    "轮候冻结",
]

# 轮候状态关键词
PENDING_KEYWORDS = ["轮候查封", "轮候冻结"]

# 轮候状态默认说明
# 根据《最高人民法院关于人民法院民事执行中查封、扣押、冻结财产的规定》第28条
DEFAULT_PENDING_NOTE = "轮候状态,真正保全期限自转为正式查封/冻结之日起算"
