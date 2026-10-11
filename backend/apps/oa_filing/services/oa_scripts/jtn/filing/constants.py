"""金诚同达 OA 立案脚本 —— 常量。"""

from __future__ import annotations

# 公共常量从 jtn.auth.constants 导入，避免重复定义
from ..auth.constants import _DEFAULT_HTTP_TIMEOUT, _HTTP_HEADERS, _LOGIN_URL

# ============================================================
# URL（立案特有）
# ============================================================
_FILING_URL = "https://ims.jtn.com/projflw/ProjectAppRegNew.aspx?t=1&&FirstModel=PROJECT&SecondModel=PROJECT003"
_PROJECT_HANDLER_BASE = "https://ims.jtn.com/Handle/ProjectAppHandler.ashx"

# 合同附件上传端点（legalup webuploader，与立案页「上传附件」按钮同源）：
# 查询参数名以 attachment.js 的 serializeParam(_upType) 为准（action/path/size/suffix，
# 实测 2026-10-11：传 uptype/dir 会返回 state=Faild）；multipart 字段名 upfile，
# 响应 {"state":"SUCCESS","url":"...","original":"..."}，成功后以
# filenamecontract_{guid} / fileurlcontract_{guid} 隐藏域随表单提交
_LEGALUP_UPLOAD_URL = "https://ims.jtn.com/js/legalup/code/LegalUp.ashx"
_LEGALUP_UPLOAD_PARAMS = {
    "encode": "utf-8",
    "action": "uploadfile",
    "path": "projectfiles",
    "size": "50",
    "suffix": "",
}

# 业务种类/子类级联选项端点（legalpro.getKind → ProCategoryGetList）：
# level=1&pid=<category> 取业务种类（id 形如 KindType03_04），
# level=2&pid=<kindtype> 取业务子类（id 形如 KindType03_0401）
_PRO_CATEGORY_LIST_URL = "https://ims.jtn.com/Handle/ProjectAppHandler.ashx/ProCategoryGetList"

# ============================================================
# XPath
# ============================================================
# 2026-08-20 起 OA 立案页委托方按钮从 div[5] 挪到 div[6]
_XPATH_ADD_CLIENT_BTN = '//*[@id="wrap"]/div[1]/div[2]/div/div[6]/div/div[1]/div[2]/a'
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
