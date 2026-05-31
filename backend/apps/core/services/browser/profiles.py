"""浏览器配置档案。

BrowserProfile 定义浏览器的运行方式，通过配置决定使用原生 launch 还是 CDP 连接。
预定义常用档案，支持环境变量覆盖。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("apps.core")

@dataclass
class BrowserProfile:
    """浏览器配置档案。

    一个档案定义一种浏览器运行方式。
    通过 cdp_url 是否为 None 决定使用原生 launch 还是 CDP 连接。
    """

    name: str
    browser_type: str = "chromium"
    headless: bool = True
    slow_mo: int = 0
    viewport: dict[str, Any] = field(default_factory=lambda: {"width": 1920, "height": 1080})
    user_agent: str | None = None
    proxy: str | None = None
    launch_args: list[str] = field(default_factory=list)
    anti_detection: bool = True
    cdp_url: str | None = None
    user_data_dir: str | None = None
    remote_url: str | None = None
    timeout: int = 30000
    navigation_timeout: int = 30000

    @classmethod
    def from_env(cls, name: str = "default") -> BrowserProfile:
        """从环境变量加载配置。

        环境变量格式: BROWSER_<NAME>_<KEY>（NAME 大写）
        例如: BROWSER_DEFAULT_HEADLESS=false, BROWSER_GSXT_CDP_URL=http://localhost:9222
        """
        prefix = f"BROWSER_{name.upper()}_"

        def _env(key: str, default: Any = None) -> Any:
            return os.environ.get(f"{prefix}{key.upper()}", default)

        def _env_bool(key: str, default: bool) -> bool:
            val = _env(key)
            if val is None:
                return default
            return val.lower() in ("true", "1", "yes")

        def _env_int(key: str, default: int) -> int:
            val = _env(key)
            if val is None:
                return default
            return int(val)

        return cls(
            name=name,
            browser_type=_env("browser_type", "chromium"),
            headless=_env_bool("headless", True),
            slow_mo=_env_int("slow_mo", 0),
            viewport=_env("viewport") or {"width": 1920, "height": 1080},
            user_agent=_env("user_agent"),
            proxy=_env("proxy"),
            launch_args=_env("launch_args", "").split(",") if _env("launch_args") else [],
            anti_detection=_env_bool("anti_detection", True),
            cdp_url=_env("cdp_url"),
            user_data_dir=_env("user_data_dir"),
            remote_url=_env("remote_url"),
            timeout=_env_int("timeout", 30000),
            navigation_timeout=_env_int("navigation_timeout", 30000),
        )

    @property
    def is_cdp(self) -> bool:
        """是否使用 CDP 连接模式。"""
        return self.cdp_url is not None

    @property
    def is_remote(self) -> bool:
        """是否连接远程 Playwright。"""
        return self.remote_url is not None

    @property
    def is_persistent(self) -> bool:
        """是否使用持久化 user_data_dir。"""
        return self.user_data_dir is not None

    def to_launch_args(self) -> dict[str, Any]:
        """转换为 playwright launch() 参数。"""
        args: dict[str, Any] = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                *self.launch_args,
            ],
        }
        if self.slow_mo > 0:
            args["slow_mo"] = self.slow_mo
        if self.proxy:
            args["proxy"] = {"server": self.proxy}
        return args

    def to_context_args(self) -> dict[str, Any]:
        """转换为 playwright new_context() 参数。"""
        args: dict[str, Any] = {
            "viewport": self.viewport,
        }
        if self.user_agent:
            args["user_agent"] = self.user_agent
        if self.proxy:
            args["proxy"] = {"server": self.proxy}
        return args

# 预定义配置档案
_PROFILES: dict[str, BrowserProfile] = {
    "default": BrowserProfile(name="default"),
    "court_zxfw": BrowserProfile(
        name="court_zxfw",
        anti_detection=True,
        slow_mo=200,
    ),
    "gsxt": BrowserProfile(
        name="gsxt",
        cdp_url="http://localhost:9222",
        anti_detection=False,
    ),
    "express": BrowserProfile(
        name="express",
        cdp_url="http://localhost:9222",
    ),
    "wechat_mp": BrowserProfile(
        name="wechat_mp",
        cdp_url="http://localhost:9223",
        user_data_dir=str(Path(__file__).resolve().parents[4] / "data" / "chrome_wechat_mp"),
        anti_detection=False,
        timeout=60000,
        navigation_timeout=60000,
    ),
}

def get_profile(name: str = "default") -> BrowserProfile:
    """获取配置档案。

    优先从环境变量加载，其次使用预定义值。
    最后检查 SystemConfig (PLAYWRIGHT_HEADED) 覆盖 headless 设置。
    """
    # 尝试从环境变量加载
    env_prefix = f"BROWSER_{name.upper()}_"
    has_env = any(k.startswith(env_prefix) for k in os.environ)
    if has_env:
        profile = BrowserProfile.from_env(name)
    elif name in _PROFILES:
        profile = _PROFILES[name]
    else:
        logger.warning("未找到浏览器配置档案 '%s'，使用默认配置", name)
        profile = _PROFILES["default"]

    # SystemConfig 覆盖 headless（CDP 模式不适用）
    if not profile.is_cdp:
        profile = _apply_headless_override(profile)

    return profile

def _apply_headless_override(profile: BrowserProfile) -> BrowserProfile:
    """检查 SystemConfig PLAYWRIGHT_HEADED，覆盖 headless 设置。"""
    import dataclasses

    try:
        from apps.core.services.system_config_service import SystemConfigService

        svc = SystemConfigService()
        headed = svc.get_value("PLAYWRIGHT_HEADED", "").lower()
        if headed in ("true", "1", "yes"):
            return dataclasses.replace(profile, headless=False)
        if headed in ("false", "0", "no"):
            return dataclasses.replace(profile, headless=True)
    except (TypeError, ValueError):
        # Django 未初始化或 DB 不可用时，使用 profile 原始值
        pass

    return profile

def register_profile(profile: BrowserProfile) -> None:
    """注册自定义配置档案。"""
    _PROFILES[profile.name] = profile
