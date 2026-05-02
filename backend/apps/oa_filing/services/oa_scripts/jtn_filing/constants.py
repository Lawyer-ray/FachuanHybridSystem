"""金诚同达 OA 立案脚本 —— 常量。"""

from __future__ import annotations

# ============================================================
# URL
# ============================================================
_LOGIN_URL = "https://ims.jtn.com/member/login.aspx"
_FILING_URL = "https://ims.jtn.com/projflw/ProjectAppRegNew.aspx?t=1&&FirstModel=PROJECT&SecondModel=PROJECT003"
_PROJECT_HANDLER_BASE = "https://ims.jtn.com/Handle/ProjectAppHandler.ashx"
_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_DEFAULT_HTTP_TIMEOUT = 20

# ============================================================
# XPath
# ============================================================
_XPATH_ADD_CLIENT_BTN = '//*[@id="wrap"]/div[1]/div[2]/div/div[5]/div/div[1]/div[2]/a'
_XPATH_PERSONAL_TAB = '//*[@id="form1"]/div[3]/div/div[1]'
_XPATH_NAME_INPUT = '//*[@id="form1"]/div[4]/div[1]/div/input'
_XPATH_ID_INPUT = '//*[@id="form1"]/div[4]/div[2]/div/input'
_XPATH_SEARCH_BTN = '//*[@id="form1"]/div[4]/a[1]'
_XPATH_RESULT_CHECKBOX = '//*[@id="form1"]/div[5]/div[2]/div[2]/table/tbody/tr/td[1]/div'
_XPATH_CONFIRM_BTN = '//*[@id="form1"]/div[5]/div[1]/div[1]/div/a[1]'
_XPATH_CREATE_NEW_BTN = '//*[@id="form1"]/div[5]/div[1]/div[1]/div/a[2]'

# ============================================================
# 客户类型映射（Chosen.js 组件）
# ============================================================
_CUSTOMER_TYPE_MAP: dict[str, str] = {
    "natural": "11",  # 自然人
    "legal": "01",  # 企业（法人）
    "non_legal_org": "01",  # 企业（非法人组织也选企业）
}

_CUSTOMER_TYPE_SUB_MAP: dict[str, str] = {
    "natural": "11-01",  # 境内自然人
    "legal": "01-08",  # 其他企业
    "non_legal_org": "01-08",
}

# ============================================================
# 等待时间（秒）
# ============================================================
_SHORT_WAIT = 1.0
_MEDIUM_WAIT = 2.0
_AJAX_WAIT = 2.5
