"""金诚同达 OA 案号查 GUID（案件管理页搜索）常量。

依据《案号查GUID方法文档.md》方法一：案件管理列表页 WebForms postback，
纯 HTTP 可完整复刻，无需浏览器。
"""

from __future__ import annotations

import re

# 案件管理列表页（PROJECT002；搜索为 WebForms postback，无 JSON 接口）
_CASE_LIST_URL = "https://ims.jtn.com/project/index.aspx?FirstModel=PROJECT&SecondModel=PROJECT002"

# postback 表单字段：案号过滤框 + 当前页码（页面 JS searchOk() 置 1 后 submit）
_SEARCH_CASE_NO_FIELD = "ctl00$ctl00$mainContentPlaceHolder$projmainPlaceHolder$project_no"
_CURRENT_PAGE_FIELD = "currentPage"

# ASP.NET 回传状态隐藏字段
_VIEWSTATE_FIELD = "__VIEWSTATE"
_VIEWSTATE_GENERATOR_FIELD = "__VIEWSTATEGENERATOR"

# 结果行操作链接携带 keyid=<GUID>（iwl_project.project_id）
_KEYID_REGEX = re.compile(r"keyid=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.IGNORECASE)

# 会话过期特征（与利冲检索同款）：~441 字节 location.replace 占位页 / 302 → member/login.aspx
_LOGIN_URL_MARKER = "member/login.aspx"
_LOCATION_REPLACE_MARKER = "location.replace"
_SESSION_PLACEHOLDER_MAX_LEN = 2048

_DEFAULT_HTTP_TIMEOUT = 20
