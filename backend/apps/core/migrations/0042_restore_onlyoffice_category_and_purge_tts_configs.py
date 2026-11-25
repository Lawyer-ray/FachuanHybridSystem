"""恢复 onlyoffice 分类 + 清掉 TTS 孤儿配置。

两件事都源于同一种账：「删模块只删了代码，没收拾数据」。

1. `onlyoffice` 分类：0036 加进 choices，0038（删 docspace 时把 choices **整份重写**）
   顺手把它一起抹掉了。后果是 3 条 `ONLYOFFICE_*` 活配置（`apps/onlyoffice/config.py`
   仍在读）的分类值变成枚举外的非法值 → admin 列表页按枚举分组，这 3 条**永远不显示**；
   编辑页分类下拉里也没有当前值 → 一保存就被迫改成别的分类。这里把分类加回来。

2. `MIMO_TTS_*`：`content_ops`（案例故事 + 播客 + TTS）在 v26.51.13 整体删除，
   changelog 写「关联配置随之清除」，但那只删了代码，库里 3 行留到现在、全仓零引用。
   这里按 key 清掉——TTS 功能已不存在，不存在误删活配置的风险。

回滚：分类枚举可反向；删掉的配置行需从执行前的 `pg_dump` 恢复（不入库，属运维备份）。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import migrations, models

logger = logging.getLogger(__name__)

#: TTS 播客模块（content_ops，v26.51.13 删除）遗留的配置 key，全仓已无消费方
_ORPHAN_TTS_KEYS = ("MIMO_TTS_MODEL", "MIMO_TTS_VOICE", "MIMO_TTS_STYLE_PROMPT")


def _purge_tts_configs(apps: Any, schema_editor: Any) -> None:
    """删掉 TTS 孤儿配置行。

    不清缓存：这些 key 已无任何读取方，且配置缓存本身有 TTL，多清一次没有收益
    （迁移里跨进程清缓存也做不到）。
    """
    SystemConfig = apps.get_model("core", "SystemConfig")
    deleted, _detail = SystemConfig.objects.filter(key__in=_ORPHAN_TTS_KEYS).delete()
    if deleted:
        logger.info("已删除 %d 行 TTS 孤儿配置：%s", deleted, ", ".join(_ORPHAN_TTS_KEYS))


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0041_llm_rate_limits"),
    ]

    operations = [
        migrations.RunPython(_purge_tts_configs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="systemconfig",
            name="category",
            field=models.CharField(
                choices=[
                    ("feishu", "飞书配置"),
                    ("dingtalk", "钉钉配置"),
                    ("wechat_work", "企业微信配置"),
                    ("telegram", "Telegram 配置"),
                    ("court_sms", "法院短信配置"),
                    ("ai", "AI 服务配置"),
                    ("llm", "LLM 大模型配置"),
                    ("enterprise_data", "企业数据配置"),
                    ("scraper", "爬虫配置"),
                    ("ocr", "OCR 服务配置"),
                    ("document_parsing", "文档解析配置"),
                    ("email", "邮件配置"),
                    ("cloud_storage", "云存储配置"),
                    ("onlyoffice", "OnlyOffice 编辑器配置"),
                    ("general", "通用配置"),
                ],
                default="general",
                help_text="配置项所属分类",
                max_length=50,
                verbose_name="分类",
            ),
        ),
    ]
