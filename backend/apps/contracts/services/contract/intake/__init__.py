"""合同自动分析导入（新建合同页拖拽上传 → LLM 抽取 → 表单草稿）。

链路边界：

- ``document_snapshot``：确定性提取文档文本（docx 段落 + 表格，pdf 取字），不调用 AI；
- ``extract_schema``：LLM 结构化输出的 Pydantic 契约；
- ``extract_service``：拼 prompt、调 LLM、受控重试；
- ``normalize``：把 LLM 的自由文本收成可入库的字面值（金额换算、枚举白名单、
  律师姓名匹配、律所识别剔除），一切不确定项标记为待人工确认。

设计红线：**AI 只产出草稿，不写库**。用户在新建页复核后才点保存，
走既有 ``ContractAdmin.save_model`` 链路。
"""

from __future__ import annotations

__all__: list[str] = []
