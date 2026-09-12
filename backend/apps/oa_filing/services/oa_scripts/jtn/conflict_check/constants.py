"""利益冲突信息预检页面 URL、XPath 常量。"""

from __future__ import annotations

# 利益冲突信息预检页面（利冲预检 - 案件审批管理）
CONFLICT_CHECK_URL = (
    "https://ims.jtn.com/projflw/projconfictfirst.aspx"
    "?FirstModel=PROJECT&SecondModel=PROJECT003&ThirdModel=PROJECT003-01"
)

# 预检关键词输入框（当事人名称）
KEYWORD_SELECTOR = "#strkeyword"

# 搜索按钮
SEARCH_BTN_SELECTOR = "#btnConflict"

# ── 等待时间（秒） ──

SHORT_WAIT = 0.5
MEDIUM_WAIT = 2
SEARCH_WAIT = 4
