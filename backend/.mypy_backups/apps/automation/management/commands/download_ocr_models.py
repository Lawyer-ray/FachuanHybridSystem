"""
下载 PP-OCRv5 Server 模型

用法:
    python manage.py download_ocr_models

注意: rapidocr>=3.4.5 会在首次使用时自动下载模型,
此命令用于预先下载模型以避免首次使用时的延迟.
"""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help: str = "预下载 PP-OCRv5 Server 模型文件"

    def handle(self, *args, **options) -> None:
        self.stdout.write("正在初始化 PP-OCRv5 Server 模型...")
        self.stdout.write("(模型会自动下载,请稍候...)")

        try:
            # 导入并初始化 OCR 引擎会触发模型下载
            from apps.automation.services.ocr import get_ocr_engine

            # 强制初始化 v5 模型
            get_ocr_engine(use_v5=True)

            self.stdout.write(self.style.SUCCESS("PP-OCRv5 Server 模型初始化成功!"))
            self.stdout.write("模型已准备就绪,可以开始使用 OCR 功能.")

        except Exception as e:
            logger.exception("操作失败")
            self.stdout.write(self.style.ERROR(f"模型初始化失败: {e}"))
            self.stdout.write("请检查网络连接后重试.")
