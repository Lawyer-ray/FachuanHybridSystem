"""虚拟模型 - 用于 Admin 界面展示"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class AutomationTool(models.Model):
    name = models.CharField(max_length=64, default="Document Processor")

    id: int

    class Meta:
        managed = False
        verbose_name = _("文档处理")
        verbose_name_plural = _("文档处理")


class NamerTool(models.Model):
    name = models.CharField(max_length=64, default="Namer Tool")

    id: int

    class Meta:
        managed = False
        verbose_name = _("自动命名工具")
        verbose_name_plural = _("自动命名工具")


class TestCourt(models.Model):
    """测试法院系统虚拟模型"""

    id: int
    name = models.CharField(max_length=64, default="Test Court")

    class Meta:
        managed = False
        verbose_name = _("测试法院系统")
        verbose_name_plural = _("测试法院系统")


class TestToolsHub(models.Model):
    """测试工具入口虚拟模型"""

    id: int
    name = models.CharField(max_length=64, default="Test Tools Hub")

    class Meta:
        managed = False
        verbose_name = _("测试工具")
        verbose_name_plural = _("测试工具")


class PreservationDateTest(models.Model):
    """财产保全日期识别测试虚拟模型"""

    id: int
    name = models.CharField(max_length=64, default="Preservation Date Test")

    class Meta:
        managed = False
        verbose_name = _("财产保全日期识别")
        verbose_name_plural = _("财产保全日期识别")


class ImageRotation(models.Model):
    """图片自动旋转工具虚拟模型"""

    id: int
    name = models.CharField(max_length=64, default="Image Rotation")

    class Meta:
        managed = False
        verbose_name = _("图片自动旋转")
        verbose_name_plural = _("图片自动旋转")
