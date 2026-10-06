"""金诚同达 OA 案号查 GUID（案件选择对话框 GET 搜索）常量。

依据《案号查GUID方法文档.md》1.4 更简变体：全站共享的案件选择对话框
searchProject.aspx（盖章/归档弹窗同源页面）接受 GET 查询参数直接搜索，
单次 GET 完成，无需 VIEWSTATE/EVENTVALIDATION，结果以 radio（value=GUID）
呈现。HTTP 会话公共常量在 jtn/auth/constants.py。
"""

from __future__ import annotations

import re

# 案件选择对话框（category 为文档实测取值；Referer 模拟从盖章页打开弹窗）
_DIALOG_URL = "https://ims.jtn.com/searchdlg/searchProject.aspx"
_DIALOG_CATEGORY = "OfficeDOC"
_DIALOG_REFERER = "https://ims.jtn.com/projdoc/officedocreg.aspx"

# GET 查询参数（与弹窗表单字段同名；均为子串包含匹配，传完整值通常唯一命中）
_PARAM_CASE_NO = "project_no"
_PARAM_CASE_NAME = "project_name"
_PARAM_CUSTOMER_NAME = "project_customer_name"

# 对话框页面特征：搜索表单的案号输入框（区分正常对话框页与异常占位页）
_DIALOG_FORM_MARKER = "project_no"

# 结果行 radio：value 即案件 GUID（iwl_project.project_id）
_RADIO_GUID_REGEX = re.compile(
    r'<input[^>]*type="radio"[^>]*value="([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"',
    re.IGNORECASE,
)

# radio value 的整值校验（lxml 路径用）
_GUID_VALUE_REGEX = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
