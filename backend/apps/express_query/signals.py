"""快递查询任务信号处理"""

from __future__ import annotations

import logging

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from apps.express_query.models import ExpressQueryTask

logger = logging.getLogger("apps.express_query")


@receiver(pre_delete, sender=ExpressQueryTask)
def delete_task_files(sender: type[ExpressQueryTask], instance: ExpressQueryTask, **kwargs: object) -> None:
    """删除任务时彻底清理所有关联文件"""
    _safe_delete_file_field(instance.waybill_image, "邮单文件")
    _safe_delete_file_field(instance.result_pdf, "结果PDF")


def _safe_delete_file_field(file_field: object, description: str) -> None:
    """安全删除 FileField 关联的物理文件（处理空值、缺失等各种边界情况）"""
    # 空值 / None / 无 name 属性 → 无需删除
    if not file_field:
        return
    if not hasattr(file_field, "name"):
        return
    name: str | None = getattr(file_field, "name", None)
    if not name:
        return

    try:
        getattr(file_field, "delete", lambda **_: None)(save=False)
        logger.info("已删除 %s: %s", description, name)
    except FileNotFoundError:
        logger.info("%s 文件已不存在: %s", description, name)
    except Exception as exc:
        logger.warning("删除 %s 失败 (%s): %s", description, type(exc).__name__, exc)
