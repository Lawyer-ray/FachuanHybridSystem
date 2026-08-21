#!/usr/bin/env python3
"""工具函数：环境变量加载、微信响应解析、httpx 兼容。"""

import json
from pathlib import Path
from typing import Any

import httpx


def load_dotenv(script_dir: Path | None = None) -> None:
    """加载 .env 文件到环境变量。"""
    if script_dir is None:
        script_dir = Path(__file__).resolve().parent
    dotenv_path = script_dir / ".env"
    if not dotenv_path.exists():
        return
    try:
        from dotenv import load_dotenv as _load

        _load(dotenv_path, override=True)
    except ModuleNotFoundError:
        pass


def parse_wechat_response(resp_json: Any) -> dict:
    """解析微信返回；errcode 不为 0 时抛出 RuntimeError。"""
    if not isinstance(resp_json, dict):
        raise RuntimeError(f"微信接口返回非 JSON 对象: {resp_json}")
    errcode = resp_json.get("errcode", 0)
    if errcode != 0:
        errmsg = resp_json.get("errmsg", "未知错误")
        raise RuntimeError(f"微信接口错误 [{errcode}]: {errmsg}")
    return resp_json


def client_kwargs(http_proxy: str | None, timeout: float = 30) -> dict:
    """组装 httpx.Client 关键字参数，兼容 0.28+ 与 0.27.x。"""
    proxy_kw = "proxy"
    try:
        httpx.Client(proxy="http://localhost")
    except TypeError:
        proxy_kw = "proxies"

    kwargs: dict[str, Any] = {"timeout": timeout, "follow_redirects": True}
    if http_proxy:
        if proxy_kw == "proxy":
            kwargs["proxy"] = http_proxy
        else:
            kwargs["proxies"] = {"http://": http_proxy, "https://": http_proxy}
    return kwargs


def _reload_env() -> None:
    """重新加载环境变量（用于 .env 变更后刷新 APPID / APPSECRET）。"""
    load_dotenv()
    from formats import APPID, APPSECRET  # noqa: F401
