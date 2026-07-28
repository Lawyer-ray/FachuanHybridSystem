"""EMS/SF 查询选择器配置 — 外置所有 DOM 选择器，便于 EMS 改版时快速更新。

加载优先级：
1. Django settings EXPRESS_QUERY_SELECTORS_PATH（JSON 文件路径）
2. 本模块内置默认值
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("apps.express_query")

# ── 内置默认配置 ───────────────────────────────────────────────

_EMS_DEFAULTS: dict[str, Any] = {
    "queryUrl": "https://www.ems.com.cn/queryList#",
    "legacyQueryUrl": "https://www.11183.com.cn/?to=%2Fquery_express_delivery",
    "cleanQueryUrl": "https://www.11183.com.cn/query_express_delivery",
    "timeouts": {
        "overall": 600,
        "login": 300,
        "captcha": 300,
        "result": 240,
        "pageLoad": 90,
        "poll": 1.2,
        "renavigateAfterUnknown": 15,
    },
    "selectors": {
        "trackingInputs": [
            "input[placeholder*='邮件号']",
            "input[placeholder*='搜索']",
            "input[placeholder*='邮件']",
            "input[placeholder*='运单']",
            "input[placeholder*='单号']",
            "input[name*='mail']",
            "input[name*='waybill']",
            "input[name*='tracking']",
            "input[id*='mail']",
            "input[id*='waybill']",
            "textarea",
            "[contenteditable='true']",
            "input[type='search']",
            "input[type='text']",
        ],
        "submitButtons": [
            "button:has-text('搜索')",
            "button:has-text('查询')",
            "button:has-text('查件')",
            "button[type='submit']",
            "a:has-text('查询')",
            "div[role='button']:has-text('查询')",
            "span[role='button']:has-text('查询')",
            "button[class*='search']",
            "button[class*='query']",
        ],
        "loginIndicators": [
            ".el-dialog.scan",
            "text=扫码登录",
            "text=请阅读并同意服务协议",
            "input[type='password']",
            "form[action*='login'] input",
        ],
        "loginEntryButtons": [
            "text=登录/注册",
            "text=登录注册",
            "text=登录",
            "a:has-text('登录/注册')",
            "span:has-text('登录/注册')",
        ],
        "loggedInIndicators": [
            "text=退出登录",
            "text=注销",
            "text=个人中心",
            "text=我的EMS",
            "text=我的账户",
            "text=用户中心",
            "text=我的快递",
        ],
        "captchaIndicators": [
            "input[placeholder*='验证码']",
            "input[aria-label*='验证码']",
            "img[src*='captcha']",
            "[class*='captcha']",
            "[id*='captcha']",
            "[class*='verify']",
        ],
        "resultContainers": [
            "[class*='timeline']",
            "[class*='track']",
            "[class*='trace']",
            "[class*='route']",
            "[class*='logistics']",
            "[class*='result']",
            "text=物流轨迹",
            "text=收寄详情",
            "text=收件人",
            "text=寄件人",
        ],
        "notFoundIndicators": [
            "text=没有查询到",
            "text=未查询到",
            "text=无查询结果",
            "text=单号不存在",
            "text=运单号不存在",
            "text=查无此单",
            "[class*='empty']",
            "[class*='no-data']",
            "[role='alert']",
        ],
        "detailButtons": [
            "button:has-text('查看详情')",
            "button:has-text('详情')",
            "button:has-text('物流详情')",
            "button:has-text('邮件详情')",
            "button:has-text('收寄详情')",
            "a:has-text('查看详情')",
            "a:has-text('详情')",
        ],
        "expandButtons": [
            "button:has-text('展开全部')",
            "span:has-text('展开全部')",
            "div:has-text('展开全部')",
            "a:has-text('展开全部')",
            "button:has-text('展开全部轨迹')",
            "span:has-text('展开全部轨迹')",
            "button:has-text('查看全部')",
            "span:has-text('查看全部')",
            "button:has-text('全部轨迹')",
            "span:has-text('全部轨迹')",
            "button:has-text('查看更多')",
            "span:has-text('查看更多')",
            "button:has-text('展开')",
            "span:has-text('展开')",
        ],
        "dismissOverlayButtons": [
            "button:has-text('知道了')",
            "button:has-text('我知道了')",
            "button:has-text('同意')",
            "button:has-text('关闭')",
            "button:has-text('跳过')",
            "button:has-text('稍后')",
            "button:has-text('确定')",
            "span:has-text('关闭')",
            "span:has-text('知道了')",
            ".close-btn",
            ".icon-close",
            "[class*='dialog'] [role='button']",
            "[class*='popup'] [role='button']",
            "[class*='mask'] [class*='close']",
        ],
        "agreementCheckboxXpaths": [
            "//*[@id='app']/div[1]/div/header/div[1]/div/div/div[3]/div/div[2]/div/div[2]/div[3]/div[1]/label/span/span",
            "//label[contains(., '同意')]/span/span",
            "//label[contains(., '服务协议')]//span[@class]",
        ],
        "agreementAcceptButtonXpaths": [
            "//*[@id='app']/div[2]/div/div[2]/div/div[1]/div[2]/div[3]/button[2]",
            "//*[@id='app']/div[2]/div/div[2]/div/div[1]/div[2]/div[3]/button[last()]",
        ],
    },
    "text": {
        "loginKeywords": ["登录/注册", "登录注册", "登录", "注册"],
        "loggedInKeywords": ["退出登录", "注销", "个人中心", "我的EMS", "我的账户", "用户中心", "我的快递"],
        "captchaKeywords": ["验证码", "安全验证", "滑块验证", "拖动滑块", "请完成验证"],
        "notFoundKeywords": ["没有查询到", "未查询到", "无查询结果", "单号不存在", "运单号不存在", "查无此单"],
        "resultKeywords": ["物流轨迹", "运单轨迹", "邮件轨迹", "已揽收", "派送", "投递", "签收", "收寄"],
        "submitButtonKeywords": ["查询", "搜索", "查件"],
        "expandKeywords": ["展开全部", "展开全部轨迹", "查看全部", "全部轨迹", "查看更多", "展开"],
        "dismissKeywords": ["知道了", "我知道了", "同意", "关闭", "跳过", "稍后", "确定"],
    },
}

_SF_DEFAULTS: dict[str, Any] = {
    "homeUrl": "https://www.sf-express.com/",
    "queryUrl": "https://www.sf-express.com/chn/sc/waybill/list",
    "timeouts": {
        "login": 300,
        "pageLoad": 30,
    },
    "selectors": {
        "loginButtons": [
            "button:has-text('登录')",
            "a:has-text('登录')",
            ".login-btn",
        ],
        "loggedInIndicators": [
            "[class*='user']",
            "[class*='avatar']",
            "text=退出登录",
        ],
        "trackingInputs": [
            "input[placeholder*='查询']",
            "input[type='text']",
        ],
        "submitButtons": [
            "button:has-text('查')",
            "button.search-icon",
        ],
        "detailButtons": [
            "button:has-text('展开详情')",
            "[role='button']:has-text('展开详情')",
            "span:has-text('展开详情')",
            "text=展开详情",
            "button:has-text('查看详情')",
        ],
        "verificationSelectors": [
            "text=收起详情",
            "text=物流轨迹",
            "text=签收时间",
            "text=签收详情",
            "text=收方",
            "text=寄方",
        ],
        "expandButtons": [
            "button:has-text('展开全部轨迹')",
            "span:has-text('展开全部轨迹')",
            "button:has-text('展开全部')",
            "span:has-text('展开全部')",
            "button:has-text('查看全部')",
            "span:has-text('查看全部')",
            "button:has-text('查看更多')",
            "span:has-text('查看更多')",
            "button:has-text('展开')",
            "span:has-text('展开')",
        ],
        "dismissOverlayButtons": [
            ".guide-close",
            ".driver-close-btn",
            "[class*='guide'] [class*='close']",
            "[class*='tour'] [class*='close']",
            "[class*='mask'] [class*='close']",
            "button[class*='skip']",
            "button:has-text('下一步')",
            "button:has-text('完成')",
            "button:has-text('跳过')",
            "button:has-text('知道了')",
            "button:has-text('我知道了')",
            "button:has-text('关闭')",
            "button:has-text('暂不')",
            "button:has-text('同意')",
            "span:has-text('下一步')",
            "span:has-text('完成')",
            "span:has-text('同意')",
            ".el-dialog__close",
            ".el-message-box__close",
        ],
    },
}

# ── 全局配置实例 ───────────────────────────────────────────────

_ems_config: dict[str, Any] = dict(_EMS_DEFAULTS)
_sf_config: dict[str, Any] = dict(_SF_DEFAULTS)
_loaded = False


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """递归合并 patch 到 base，patch 中的键覆盖 base。"""
    out = dict(base)
    for key in set(list(base.keys()) + list(patch.keys())):
        if key in patch and key in base and isinstance(base[key], dict) and isinstance(patch[key], dict):
            out[key] = _deep_merge(base[key], patch[key])
        elif key in patch:
            out[key] = patch[key]
    return out


def _load_from_file() -> None:
    """尝试从 Django settings 指定的 JSON 文件加载覆盖配置。"""
    global _loaded
    if _loaded:
        return
    _loaded = True

    try:
        from django.conf import settings

        path_str = getattr(settings, "EXPRESS_QUERY_SELECTORS_PATH", "")
        if not path_str:
            return
        path = Path(path_str)
        if not path.exists():
            logger.warning("Express query selectors file not found: %s", path)
            return
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("ems"), dict):
            global _ems_config
            _ems_config = _deep_merge(_EMS_DEFAULTS, data["ems"])
        if isinstance(data.get("sf"), dict):
            global _sf_config
            _sf_config = _deep_merge(_SF_DEFAULTS, data["sf"])
        logger.info("Loaded express query selectors from %s", path)
    except Exception:
        logger.debug("No express query selectors override loaded, using defaults")


def get_ems_config() -> dict[str, Any]:
    """返回 EMS 查询配置（合并用户覆盖）。"""
    _load_from_file()
    return _ems_config


def get_sf_config() -> dict[str, Any]:
    """返回顺丰查询配置（合并用户覆盖）。"""
    _load_from_file()
    return _sf_config


def get_ems_selectors(key: str) -> list[str]:
    """快捷方法：获取 EMS 选择器列表。"""
    return list(get_ems_config().get("selectors", {}).get(key, []))


def get_ems_timeouts() -> dict[str, int | float]:
    """快捷方法：获取 EMS 超时配置。"""
    return dict(get_ems_config().get("timeouts", {}))


def get_ems_text(key: str) -> list[str]:
    """快捷方法：获取 EMS 文本关键词列表。"""
    return list(get_ems_config().get("text", {}).get(key, []))
