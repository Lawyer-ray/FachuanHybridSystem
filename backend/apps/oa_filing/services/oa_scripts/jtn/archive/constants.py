"""归档页面 URL、XPath 常量。"""

from __future__ import annotations

# 结案归档管理 - 结案申请页面
ARCHIVE_PAGE_URL = "https://ims.jtn.com/projclose/projcloseapp.aspx?&FML=PROJECT&SML=PROJECT008&TML=PROJECT008-01"

# 案件小结 textarea ID（readonly，需 JS 去除 readonly）
DESCRIPTION_SELECTOR = "#proje_report1"

# 保存按钮 ID
SAVE_BTN_ID = "ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_btnSave"

# ── 案件搜索弹窗（共用盖章的 iframe 关键词） ──

_POPUP_IFRAME_KEYWORD = "searchProject"

# ── iframe 内常量 ──

IFRAME_PROJECT_NO_SELECTOR = "#project_no"
IFRAME_SEARCH_FN = "fnseach()"

# ── 等待时间（秒） ──

SHORT_WAIT = 0.5
MEDIUM_WAIT = 2
AJAX_WAIT = 3
POPUP_WAIT = 3
