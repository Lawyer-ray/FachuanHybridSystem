"""金诚同达 OA 案号查 GUID（案件管理页搜索 + 飞连一键登录自愈）常量。

搜索机制=方法一（案件管理列表页 WebForms postback）：对表单登录会话可靠
（2026-10-12 实测：同一会话下列表页能搜到的案件，searchdlg 对话框 GET 直搜
返回 TotalCount=0——对话框只认浏览器 SSO 派生的会话，故不用对话框）。

会话自愈新增第三层：SSO 门户登录页（access.jtn.com/login，飞连 SPA）无法
账密登录（JTN 租户仅一键/扫码/短信），但「桌面一键登录」可纯 HTTP 复刻——
本机飞连客户端在 127.0.0.1:31080 暴露 /v1/quick-login，签发一次性 token，
POST 到门户 /api/quick-login 即可恢复 SSO 会话（2026-10-12 实测打通）。
"""

from __future__ import annotations

import re

# 案件管理列表页（PROJECT002；搜索为 WebForms postback，无 JSON 接口）
_CASE_LIST_URL = "https://ims.jtn.com/project/index.aspx?FirstModel=PROJECT&SecondModel=PROJECT002"

# postback 表单字段：三个过滤框同一机制（子串包含匹配），按需只传一个
_SEARCH_CASE_NO_FIELD = "ctl00$ctl00$mainContentPlaceHolder$projmainPlaceHolder$project_no"
_SEARCH_CASE_NAME_FIELD = "ctl00$ctl00$mainContentPlaceHolder$projmainPlaceHolder$project_name"
_SEARCH_CUST_NAME_FIELD = "ctl00$ctl00$mainContentPlaceHolder$projmainPlaceHolder$project_cust_name"
_CURRENT_PAGE_FIELD = "currentPage"

# ASP.NET 回传状态隐藏字段
_VIEWSTATE_FIELD = "__VIEWSTATE"
_VIEWSTATE_GENERATOR_FIELD = "__VIEWSTATEGENERATOR"

# 结果行操作链接携带 keyid=<GUID>（iwl_project.project_id）
_KEYID_REGEX = re.compile(r"keyid=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.IGNORECASE)

# ── SSO 门户一键登录自愈（本机飞连客户端） ──

# 门户登录页特征（区别于 corplink 网关回调：后者吃 Set-Cookie 即放行，前者需恢复会话）
_SSO_PORTAL_LOGIN_MARKER = "access.jtn.com/login"

# 本机飞连客户端一键登录端点（CORS 仅放行 access.jtn.com 来源）
_LOCAL_QUICK_LOGIN_URL = "http://127.0.0.1:31080/v1/quick-login"
_LOCAL_QUICK_LOGIN_ORIGIN = "https://access.jtn.com"

# 门户兑换一次性 token 的接口（token 换 SSO 会话 cookie）；os=web 必须
# 携带——缺了它门户按非 web 客户端判「当前登录方式未开启」（194008）
_SSO_QUICK_LOGIN_URL = "https://access.jtn.com/api/quick-login?os=web"
_SSO_QUICK_LOGIN_SCENE = "feilian"

# 门户会话 cookie 名（缓存扁平值过期后与门户新下发同名共存，恢复前须清扁平值）
_PORTAL_SESSION_COOKIE_NAMES = frozenset({"session", "csrf-token"})
