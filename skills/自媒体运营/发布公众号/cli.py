#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号草稿箱发布工具 — 命令行入口。

用法:
    python3 cli.py --title "标题" --digest "摘要" --markdown article.md --cover cover.jpg
    python3 cli.py --title "标题" --digest "摘要" --html   article.html  --cover cover.jpg

前置条件:
    - 同级目录 .env 中配置 WECHAT_APPID / WECHAT_APPSECRET
    - pip install httpx python-dotenv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from auth import get_access_token
from client import create_draft, upload_image
from converter import markdown_to_html, wrap_full_html
from utils import load_dotenv

logger = logging.getLogger("wechat_draft")


def _setup_logging(level: int = logging.INFO) -> None:
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(level)


def _read_html(path: Path, title: str) -> str:
    raw = path.read_text(encoding="utf-8")
    return raw if "<html" in raw.lower() else wrap_full_html(raw, title)


def _read_markdown(path: Path, title: str) -> str:
    body = markdown_to_html(path.read_text(encoding="utf-8"))
    return wrap_full_html(body, title)


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="发布公众号图文草稿（保存到草稿箱）")
    parser.add_argument("--title", required=True, help="文章标题（≤64 字节）")
    parser.add_argument("--digest", required=True, help="文章摘要（≤120 字节）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--html", dest="html_fp", help="正文 HTML 文件路径")
    group.add_argument("--markdown", dest="md_fp", help="正文 Markdown 文件路径")
    parser.add_argument(
        "--cover", required=True, help="封面图（请自行裁剪为 900×383，2.35:1）"
    )
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--force-refresh-token", action="store_true")
    args = parser.parse_args()

    # 读取正文
    if args.html_fp:
        path = Path(args.html_fp)
        if not path.exists():
            logger.error("HTML 文件不存在: %s", path)
            return 1
        raw_html = _read_html(path, args.title)
    else:
        path = Path(args.md_fp)
        if not path.exists():
            logger.error("Markdown 文件不存在: %s", path)
            return 1
        raw_html = _read_markdown(path, args.title)

    # 调用 API
    logger.info("① 获取 access_token ...")
    token = get_access_token(force_refresh=args.force_refresh_token)

    logger.info("② 上传封面图 ...")
    thumb_media_id = upload_image(token, args.cover)

    logger.info("③ 创建草稿 ...")
    draft_id = create_draft(
        token=token,
        title=args.title,
        digest=args.digest,
        content_html=raw_html,
        thumb_media_id=thumb_media_id,
    )

    # 输出
    logger.info("草稿保存成功！")
    logger.info("   标题   : %s", args.title)
    logger.info("   摘要   : %s", args.digest)
    if not args.no_preview:
        preview = args.digest if len(args.digest) <= 80 else args.digest[:77] + "..."
        logger.info("   预览   : %s", preview)
    logger.info("   草稿ID : %s", draft_id)
    logger.info("   >>> 前往 mp.weixin.qq.com →「内容与互动」→「草稿箱」查看和发布")
    return 0


if __name__ == "__main__":
    _setup_logging()
    sys.exit(main())
