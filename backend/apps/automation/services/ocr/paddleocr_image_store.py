"""PaddleOCR 图片落盘（从 ``paddleocr_api_service`` 拆分出来，2026-11-27）。

与 HTTP adapter 无关：收「已下载图片 + 注入的 storage」，把字节写进存储，
返回 ``{图片 key: 已保存路径}``。调用方（Django 侧）传 ``default_storage``，
脚本侧传本地实现，测试侧传内存实现——所以本模块不在模块级绑 Django storage。
"""

from __future__ import annotations

import logging
from typing import Any

from .paddleocr_response_parser import PaddleOCRApiImage

logger = logging.getLogger(__name__)


def persist_images(
    images: list[PaddleOCRApiImage],
    *,
    storage: Any,
    prefix: str,
) -> dict[str, str]:
    """把已下载的图片写入任意 storage（Django ``default_storage`` 或同接口对象）。

    为什么接收 ``storage`` 而不是直接 ``from django.core.files.storage import
    default_storage``：OCR 引擎是纯传输层，被 Celery 任务、管理命令、单测直接调用。
    在模块级硬绑 Django storage 会让它无法在非 Django 上下文裸跑（也拉不进单测）。
    所以落盘能力做成「调用方注入 storage」：Django 侧传 ``default_storage``，
    脚本侧传本地实现，测试侧传内存实现。

    文件命名：以图片自身的 key（``imgs/img_in_seal_box_762_886.jpg``）为基准，
    丢弃目录部分后拼到 ``prefix`` 下。这样「正文里引的是哪个 key」与「存的是哪个
    文件」可以靠文件名对上，方便把 Markdown 里的死链改写成真实地址。

    Args:
        images: 已下载图片（``data`` 为 None 的会被跳过）
        storage: 需提供 ``save(name, content) -> str``
        prefix: 存储前缀目录，如 ``pdf_splitting/ocr_images/{hash}/p031``

    Returns:
        ``{图片 key: 已保存的相对路径}``；未存盘的 key 不出现在结果里。
    """
    if not images or not prefix:
        return {}

    from pathlib import PurePosixPath

    # 延迟 import：ContentFile 只在「真的落盘」时才需要，而本模块被大量单测/脚本
    # 直接 import。把它提到模块顶会让非 Django 上下文也背上这个依赖。
    from django.core.files.base import ContentFile

    saved: dict[str, str] = {}
    for image in images:
        if image.data is None:
            continue
        # key 可能是 ``imgs/xxx.jpg``，只取文件名；不回退到底线字符以外的推导，
        # 因为真实 key 总是带扩展名的扁平文件名。
        filename = PurePosixPath(image.key).name or "image.jpg"
        rel_path = f"{prefix.rstrip('/')}/{filename}"
        try:
            # storage.save 遇到同名会改名（page_0001_x1y2.jpg）。先删旧文件
            # 让重跑同一页时覆盖而不是累积残档——与 ocr_cache 的处理一致。
            if storage.exists(rel_path):
                storage.delete(rel_path)
            saved_path = storage.save(rel_path, ContentFile(image.data))
        except Exception:
            # 单张写盘失败不能让整页识别作废（磁盘满/权限/存储后端抖动）。
            logger.exception("PaddleOCR 图片写盘失败: key=%s", image.key)
            continue
        saved[image.key] = str(saved_path)

    logger.info("PaddleOCR 图片写盘完成: %d/%d -> %s", len(saved), len(images), prefix)
    return saved
