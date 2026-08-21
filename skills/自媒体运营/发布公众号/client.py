#!/usr/bin/env python3
"""微信 API 客户端：上传封面图、创建草稿。"""

import mimetypes
from pathlib import Path

import httpx
from formats import AUTHOR, DRAFT_URL, UPLOAD_URL
from utils import client_kwargs, parse_wechat_response


def upload_image(token: str, image_path: str) -> str:
    """
    上传封面图，原图直传不裁剪。
    用户需自行确保比例正确（推荐 900×383，2.35:1）。
    """
    src = Path(image_path)
    if not src.exists():
        raise RuntimeError(f"封面图不存在: {image_path}")

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

    from formats import HTTP_PROXY

    kwargs = client_kwargs(http_proxy=HTTP_PROXY, timeout=30)
    url = f"{UPLOAD_URL}?access_token={token}"

    with httpx.Client(**kwargs) as client:
        resp = client.post(url, content=body, headers=headers)
        resp.raise_for_status()
        data = parse_wechat_response(resp.json())

    media_id = data.get("media_id")
    if not media_id:
        raise RuntimeError(f"上传图片未返回 media_id: {data}")
    return media_id


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

    from formats import HTTP_PROXY

    kwargs = client_kwargs(http_proxy=HTTP_PROXY, timeout=30)
    url = f"{DRAFT_URL}?access_token={token}"
    headers = {"Content-Type": "application/json; charset=utf-8"}

    with httpx.Client(**kwargs) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = parse_wechat_response(resp.json())

    return str(data["media_id"])
