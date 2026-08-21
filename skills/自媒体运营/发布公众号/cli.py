#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号草稿箱发布工具

用法:
    1. 复制 .env.example 为 .env，填写你家公众号的 AppID / AppSecret
    2. 用 Markdown 或 HTML 写好正文；用外部工具自行制作封面图（推荐 900×383，2.35:1）
    3. 运行:
       python3 cli.py --title "标题" --digest "摘要" --html article.html --cover cover.jpg
       或
       python3 cli.py --title "标题" --digest "摘要" --markdown article.md --cover cover.jpg

前置条件:
    - 公众号已启用「开发→基本配置」，已获取 AppID 与 AppSecret
    - 本机公网 IP 已加入公众号白名单（如需）
    - uv pip install -e .
"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# ============ Logging ============
logger = logging.getLogger("wechat_draft")


def _setup_logging(level: int = logging.INFO) -> None:
    """配置日志格式。"""
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "[%(name)s] %(levelname)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)


# ============ 自带 .env 加载 ============
_SCRIPT_DIR = Path(__file__).resolve().parent
_DOTENV_PATH = _SCRIPT_DIR / ".env"
if _DOTENV_PATH.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(_DOTENV_PATH, override=True)
    except ModuleNotFoundError:
        pass

# ============ 配置（优先从环境变量读取） ============
APPID: str | None = os.getenv("WECHAT_APPID")
APPSECRET: str | None = os.getenv("WECHAT_APPSECRET")
AUTHOR: str = os.getenv("AUTHOR", "作者")

_HTTP_PROXY: str | None = os.getenv("HTTP_PROXY") or os.getenv("https_proxy")

# 本地 token 缓存（7200 秒有效期，脚本自动复用）
_TOKEN_CACHE_FILE = _SCRIPT_DIR / "token_cache.json"

# 微信接口常量
TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
UPLOAD_URL = "https://api.weixin.qq.com/cgi-bin/media/uploadimg"
DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"


# ============ Proxy 配置 ============
def _get_proxies() -> dict[str, str] | None:
    """返回 httpx 代理配置。"""
    if _HTTP_PROXY:
        return {"http://": _HTTP_PROXY, "https://": _HTTP_PROXY}
    return None


# ============ Config 校验 ============
def _ensure_config() -> tuple[str, str]:
    """校验 AppID / AppSecret 已配置。"""
    appid = APPID
    appsecret = APPSECRET
    missing: list[str] = []
    if not appid:
        missing.append("WECHAT_APPID")
    if not appsecret:
        missing.append("WECHAT_APPSECRET")
    if missing:
        tmpl = _SCRIPT_DIR / ".env.example"
        logger.error(
            "缺少环境变量: %s\n"
            "\n请在 %s 中填写:\n"
            "  WECHAT_APPID=你的AppID\n"
            "  WECHAT_APPSECRET=你的AppSecret\n"
            "\n模板参考: %s",
            ", ".join(missing),
            str(_SCRIPT_DIR / ".env"),
            str(tmpl),
        )
        sys.exit(1)
    return str(appid), str(appsecret)


# ============ Token 缓存 ============
def _load_cached_token() -> tuple[str, float] | None:
    """读本地缓存的 access_token 和过期时间戳。"""
    if not _TOKEN_CACHE_FILE.exists():
        return None
    try:
        cache = json.loads(_TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
        token = cache.get("access_token")
        expires_at = cache.get("expires_at", 0)
        if token and expires_at > time.time():
            return token, expires_at
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _save_token_cache(token: str, expires_in: int) -> None:
    """把 token 写到本地缓存。"""
    cache = {
        "access_token": token,
        "expires_at": time.time() + expires_in - 120,  # 提前 120 秒过期，留余量
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        _TOKEN_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# ============ 微信响应解析 ============
def _parse_wechat_response(resp_json: Any) -> dict:
    """统一解析微信返回; 如果包含 errcode 不为 0，抛出异常。"""
    if not isinstance(resp_json, dict):
        msg = f"微信接口返回非 JSON 对象: {resp_json}"
        raise RuntimeError(msg)
    errcode = resp_json.get("errcode", 0)
    if errcode != 0:
        errmsg = resp_json.get("errmsg", "未知错误")
        msg = f"微信接口错误 [{errcode}]: {errmsg}"
        raise RuntimeError(msg)
    return resp_json


# ============ Access Token ============
def get_access_token(force_refresh: bool = False) -> str:
    """获取 access_token（优先本地缓存，避免频繁请求）。"""
    if not force_refresh:
        cached = _load_cached_token()
        if cached:
            token, expires_at = cached
            expire_str = time.strftime("%H:%M:%S", time.localtime(expires_at))
            logger.info("使用缓存 token（到期 %s）", expire_str)
            return token

    appid, appsecret = _ensure_config()
    logger.info("请求新 token ...")

    params = {
        "grant_type": "client_credential",
        "appid": appid,
        "secret": appsecret,
    }
    proxies = _get_proxies()

    with httpx.Client(proxies=proxies, timeout=15, follow_redirects=True) as client:
        resp = client.get(TOKEN_URL, params=params)
        resp.raise_for_status()
        data = _parse_wechat_response(resp.json())

    token = str(data["access_token"])
    expires_in = data.get("expires_in", 7200)
    _save_token_cache(token, expires_in)
    return token


# ============ 上传封面图 ============
def upload_image(token: str, image_path: str) -> str:
    """
    上传封面图到微信服务器，返回 media_id。
    使用 uploadimg 接口（临时素材，不占永久素材配额）。
    """
    src = Path(image_path)
    if not src.exists():
        msg = f"封面图不存在: {image_path}"
        raise RuntimeError(msg)

    mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    filename = src.name

    with open(image_path, "rb") as f:
        file_bytes = f.read()

    boundary = "----WechatFormBoundary"
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += (
        f'Content-Disposition: form-data; name="media"; '
        f'filename="{filename}"\r\n'
    ).encode()
    body += f"Content-Type: {mime}\r\n\r\n".encode()
    body += file_bytes
    body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    proxies = _get_proxies()
    url = f"{UPLOAD_URL}?access_token={token}"

    with httpx.Client(proxies=proxies, timeout=30, follow_redirects=True) as client:
        resp = client.post(url, content=body, headers=headers)
        resp.raise_for_status()
        data = _parse_wechat_response(resp.json())

    media_id = data.get("media_id")
    url_in_resp = data.get("url")
    if not media_id:
        msg = f"上传图片未返回 media_id: {data}"
        raise RuntimeError(msg)
    logger.info("封面上传成功，media_id=%s, url=%s", media_id, url_in_resp)
    return media_id


# ============ Markdown → HTML 极简转换 ============
def _inline_format(text: str) -> str:
    """处理行内格式：加粗、斜体。"""
    # **加粗**
    while "**" in text:
        parts = text.split("**", 2)
        if len(parts) < 3:
            break
        text = f"{parts[0]}<strong>{parts[1]}</strong>{parts[2]}"
    # *斜体*
    while text.count("*") >= 2:
        parts = text.split("*", 2)
        if len(parts) < 3:
            break
        text = f"{parts[0]}<em>{parts[1]}</em>{parts[2]}"
    return text


def _markdown_to_html(md_text: str) -> str:
    """极简 Markdown 转 HTML，适合公众号图文正文。"""
    lines = md_text.splitlines()
    html_lines: list[str] = []
    in_blockquote = False
    in_list = False

    def flush_blockquote() -> None:
        nonlocal in_blockquote
        if in_blockquote:
            html_lines.append("</blockquote>")
            in_blockquote = False

    def flush_list() -> None:
        nonlocal in_list
        if in_list:
            html_lines.append("</ol>")
            in_list = False

    for line in lines:
        stripped = line.strip()

        # 空行
        if not stripped:
            flush_blockquote()
            flush_list()
            html_lines.append("<p>&nbsp;</p>")
            continue

        # 代码块 ```
        if stripped.startswith("```"):
            flush_blockquote()
            flush_list()
            html_lines.append("<p><strong>代码块</strong></p>")
            continue

        # 引用
        if stripped.startswith("> "):
            if not in_blockquote:
                flush_list()
                html_lines.append("<blockquote>")
                in_blockquote = True
            content = stripped[2:].strip()
            html_lines.append(f"<p>{_inline_format(content)}</p>")
            continue

        flush_blockquote()

        # 有序列表 1. xxx
        if len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == ".":
            if not in_list:
                html_lines.append("<ol>")
                in_list = True
            content = stripped.split(".", 1)[1].strip()
            html_lines.append(f"<li>{_inline_format(content)}</li>")
            continue

        flush_list()

        # 标题
        if stripped.startswith("# "):
            html_lines.append(f"<h2>{_inline_format(stripped[2:])}</h2>")
            continue
        if stripped.startswith("## "):
            html_lines.append(f"<h3>{_inline_format(stripped[3:])}</h3>")
            continue
        if stripped.startswith("### "):
            html_lines.append(f"<h4>{_inline_format(stripped[4:])}</h4>")
            continue

        # 普通段落
        html_lines.append(f"<p>{_inline_format(stripped)}</p>")

    flush_blockquote()
    flush_list()

    return "".join(html_lines)


def generate_full_html(body_html: str, title: str = "") -> str:
    """把正文 HTML 包装成完整页面（带微信友好基础样式）。"""
    style = (
        "font-family: -apple-system, \"PingFang SC\", \"Helvetica Neue\", "
        "Helvetica, Arial, sans-serif; font-size: 17px; line-height: 1.8; "
        "color: #333; max-width: 680px; margin: 0 auto; padding: 16px;"
    )
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
body {{ {style} }}
h2 {{ font-size: 20px; font-weight: bold; margin-top: 24px; margin-bottom: 12px; }}
h3 {{ font-size: 18px; font-weight: bold; margin-top: 20px; margin-bottom: 10px; }}
p {{ margin: 14px 0; text-align: justify; word-break: break-word; }}
strong {{ font-weight: bold; }}
blockquote {{ border-left: 4px solid #ddd; padding-left: 14px; color: #666; margin: 16px 0; }}
li {{ margin: 8px 0; }}
</style>
</head>
<body>
<body_html_placeholder>
</body>
</html>
""".replace("<body_html_placeholder>", body_html)


# ============ 创建草稿 ============
def create_draft(
    token: str,
    title: str,
    digest: str,
    content_html: str,
    thumb_media_id: str,
    author: str | None = None,
) -> str:
    """调用微信公众号草稿接口，返回 draft media_id。"""
    payload = {
        "articles": [
            {
                "title": title,
                "author": author or AUTHOR,
                "digest": digest,
                "content": content_html,
                "thumb_media_id": thumb_media_id,
                "need_open_comment": 1,
                "only_fans_can_comment": 0,
            }
        ]
    }

    url = f"{DRAFT_URL}?access_token={token}"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    proxies = _get_proxies()

    with httpx.Client(proxies=proxies, timeout=30, follow_redirects=True) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = _parse_wechat_response(resp.json())

    draft_id = str(data["media_id"])
    return draft_id


# ============ CLI ============
def main() -> int:
    parser = argparse.ArgumentParser(
        description="发布公众号图文草稿（保存到草稿箱）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--title", required=True, help="文章标题（≤64 字节）")
    parser.add_argument("--digest", required=True, help="文章摘要（≤120 字节）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--html", dest="html_file", help="正文 HTML 文件路径")
    group.add_argument("--markdown", dest="md_file", help="正文 Markdown 文件路径")
    parser.add_argument(
        "--cover", required=True, help="封面图路径（请自行裁剪为 900×383，2.35:1）"
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="不在终端打印正文预览",
    )
    parser.add_argument(
        "--force-refresh-token",
        action="store_true",
        help="强制刷新 access_token（Token 有问题时尝试）",
    )
    args = parser.parse_args()

    # ---- 1. 读取正文 ----
    raw_html: str
    if args.html_file:
        path = Path(args.html_file)
        if not path.exists():
            logger.error("错误: HTML 文件不存在: %s", path)
            return 1
        raw_html = path.read_text(encoding="utf-8")
        # 如果不是完整 HTML，包装一下
        if "<html" not in raw_html.lower():
            raw_html = generate_full_html(raw_html, args.title)
    else:  # Markdown
        path = Path(args.md_file)
        if not path.exists():
            logger.error("错误: Markdown 文件不存在: %s", path)
            return 1
        md_text = path.read_text(encoding="utf-8")
        body_html = _markdown_to_html(md_text)
        raw_html = generate_full_html(body_html, args.title)

    # ---- 2. 获取 token ----
    logger.info("① 获取 access_token ...")
    token = get_access_token(force_refresh=args.force_refresh_token)

    # ---- 3. 上传封面 ----
    logger.info("② 上传封面图 ...")
    thumb_media_id = upload_image(token, args.cover)

    # ---- 4. 创建草稿 ----
    logger.info("③ 创建草稿 ...")
    draft_id = create_draft(
        token=token,
        title=args.title,
        digest=args.digest,
        content_html=raw_html,
        thumb_media_id=thumb_media_id,
    )

    # ---- 5. 输出结果 ----
    logger.info("草稿保存成功！")
    logger.info("   标题   : %s", args.title)
    logger.info("   摘要   : %s", args.digest)
    if not args.no_preview:
        preview = (
            args.digest
            if len(args.digest) <= 80
            else args.digest[:77] + "..."
        )
        logger.info("   预览   : %s", preview)
    logger.info("   草稿ID : %s", draft_id)
    logger.info("   >>> 前往 mp.weixin.qq.com →「内容与互动」→「草稿箱」查看和发布")

    return 0


if __name__ == "__main__":
    _setup_logging()
    sys.exit(main())
