"""盖章页面 URL、XPath 常量。"""

from __future__ import annotations

# 盖章文书管理页面
STAMP_PAGE_URL = "https://ims.jtn.com/projdoc/officedocreg.aspx?&FirstModel=PROJECT&SecondModel=PROJECT005"

# 弹窗 iframe URL 关键词
_POPUP_IFRAME_KEYWORD = "searchProject"

# ── 主页面 XPaths ──

# 搜索案件按钮（放大镜图标）
XPATH_SEARCH_CASE_BTN = '//*[@id="wrap"]/div[1]/div[2]/div/div[5]/table/tbody/tr[3]/td[2]/a'

# 文档类型下拉菜单
XPATH_FILE_TYPE = '//*[@id="file_type_1"]'

# 预盖章份数输入框
XPATH_STAMP_COPIES = '//*[@id="file_ForecastCount_1"]'

# 保存按钮
XPATH_SAVE_BTN = '//*[@id="ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_btnSave"]'

# ── 案件搜索弹窗（iframe 内） ──

# 案件编号输入框（readonly，需 JS 去除 readonly）
IFRAME_PROJECT_NO_SELECTOR = "#project_no"

# 搜索函数名（JS 调用）
IFRAME_SEARCH_FN = "fnseach()"

# ── 文档类型选项值 ──

FILE_TYPE_SOUHAN = "0000000029"  # 所函

# ── 盖章类型 checkbox 索引（li 从 1 开始） ──

STAMP_TYPE_INDEX_GONGZHANG = 1  # 公章
STAMP_TYPE_INDEX_DIANZI = 3  # 电子公章

# ── 默认值 ──

DEFAULT_STAMP_COPIES = 3

# ── 等待时间（秒） ──

SHORT_WAIT = 0.5
MEDIUM_WAIT = 2
AJAX_WAIT = 3
UPLOAD_WAIT = 6
POPUP_WAIT = 3
