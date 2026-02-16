"""
自动化相关 Prompt 模板

定义用于法院文书识别等自动化场景的 Prompt 模板.
"""

from .base import CodePromptTemplate, PromptManager

AUTOMATION_SUMMONS_INFO_EXTRACT = CodePromptTemplate(
    name="automation_summons_info_extract",
    template="""请从以下传票内容中提取案号和开庭时间.

传票内容:
{text}

提取要求:
1. 案号格式:(年份)法院代码+案件类型字号+序号+号
   - 年份:4位数字,如2024、2025
   - 法院代码:省份简称+区县代码,如"粤0604"、"京0105"、"沪0115"
   - 案件类型字号(必须包含):民初、民终、刑初、刑终、执、执保、执异、执恢、破、行初、行终等
   - 序号:数字
   - 必须以"号"字结尾
   - 示例:(2024)粤0604民初41257号、(2025)京0105刑初12345号

2. 重要:案号中必须包含案件类型字号(如民初、民终、刑初等),不能省略!
   - 错误示例:(2025)粤060441257(缺少案件类型)
   - 正确示例:(2025)粤0604民初41257号

3. 开庭时间需要包含完整的日期和时间,格式为:YYYY-MM-DD HH:MM

4. 如果无法确定某个字段,请返回 null

请严格按照以下 JSON 格式返回结果,不要包含其他内容:
{{"case_number": "案号或null", "court_time": "YYYY-MM-DD HH:MM或null"}}
""",
    description="从传票中提取案号与开庭时间(JSON 输出)",
    variables=["text"],
)

AUTOMATION_EXECUTION_INFO_EXTRACT = CodePromptTemplate(
    name="automation_execution_info_extract",
    template="""请从以下执行裁定书中提取案号和财产保全到期时间.

裁定书内容:
{text}

提取要求:
1. 案号格式:(年份)法院代码+案件类型字号+序号+号
   - 年份:4位数字,如2024、2025
   - 法院代码:省份简称+区县代码,如"粤0604"、"京0105"
   - 案件类型字号(必须包含):执、执保、执异、执恢、民初、民终等
   - 序号:数字
   - 必须以"号"字结尾
   - 示例:(2024)粤0604执保12345号、(2025)京0105执12345号

2. 重要:案号中必须包含案件类型字号,不能省略!

3. 财产保全到期时间格式为:YYYY-MM-DD

4. 如果无法确定某个字段,请返回 null

请严格按照以下 JSON 格式返回结果,不要包含其他内容:
{{"case_number": "案号或null", "preservation_deadline": "YYYY-MM-DD或null"}}
""",
    description="从执行裁定书中提取案号与保全到期时间(JSON 输出)",
    variables=["text"],
)


PromptManager.register(AUTOMATION_SUMMONS_INFO_EXTRACT)
PromptManager.register(AUTOMATION_EXECUTION_INFO_EXTRACT)
