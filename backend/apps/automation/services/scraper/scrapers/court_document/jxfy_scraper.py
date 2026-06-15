"""
江西电子送达平台 (sfsd.jxfy.gov.cn) 文书下载爬虫

与湖北电子送达平台 (dzsd.hbfy.gov.cn) 使用同一套"司法送达网"系统
（上海道律信息技术有限公司），接口结构一致，仅域名不同。

支持账号密码登录模式（/sfsddz）。
"""

from __future__ import annotations

import re
from typing import Any

from .daolv_sifa_songda_scraper import DaolvSifaSongdaScraper


class JxfyCourtScraper(DaolvSifaSongdaScraper):  # pragma: no cover
    """江西电子送达爬虫（与湖北同平台，域名不同）"""

    # 纯 HTTP 请求，不需要 Playwright 浏览器
    requires_browser = False

    # ── 道律平台域名配置 ────────────────────────────────────────
    _DOMAIN = "sfsd.jxfy.gov.cn"
    _LOGIN_PAGE_URL = "http://sfsd.jxfy.gov.cn/sfsddz"
    _CAPTCHA_IMAGE_URL = "http://sfsd.jxfy.gov.cn:80/deli/images/yanz.png"
    _CAPTCHA_CHECK_URL = "http://sfsd.jxfy.gov.cn:80/deli/deli-login!checkyzmAjaxp.action"
    _LOGIN_URL = "http://sfsd.jxfy.gov.cn:80/deli/easy-login!dologinAjax.action"
    _MAIN_URL = "http://sfsd.jxfy.gov.cn:80/deli/login!main.action"
    _LIST_URLS = (
        "http://sfsd.jxfy.gov.cn:80/deli/TdeliPubRecord/tdelipubrecord!todoList.action",
        "http://sfsd.jxfy.gov.cn:80/deli/TdeliPubRecord/tdelipubrecord!doneList.action",
        "http://sfsd.jxfy.gov.cn:80/deli/TdeliPubRecord/tdelipubrecord!expiredList.action",
    )
    _PASSWORD_PATTERN = re.compile(r"密码[：:]\s*([0-9A-Za-z]+)")
    _PLATFORM_LABEL = "江西"

    # 凭证配置 key（优先尝试 jxfy_*，回退到 hbfy_*）
    _CREDENTIAL_CONFIG_KEYS = ("jxfy_account", "jxfy_password")

    def run(self) -> dict[str, Any]:  # pragma: no cover
        url = self.task.url
        if "sfsd.jxfy.gov.cn/sfsddz" in url:
            return self._run_account_mode(source_domain="sfsd.jxfy.gov.cn")
        raise ValueError(f"不支持的江西送达链接: {url}")
