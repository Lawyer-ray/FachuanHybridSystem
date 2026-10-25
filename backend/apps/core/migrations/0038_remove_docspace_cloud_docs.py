"""移除 OnlyOffice DocSpace 云文档功能（已由本地 Document Server 取代）。

`apps.docspace` 应用整体删除后需要清理三处残留：
1. `SystemConfig.Category` 去掉 `docspace` 枚举值（下拉不再出现该分类）；
2. `core_systemconfig` 里遗留的 DOCSPACE_* 配置行（含云端 portal 地址与加密 token）；
3. 孤儿表 `docspace_docspacedocument`（app 删除后 Django 不再管理该表）。

反向操作只恢复枚举值，不恢复数据（原表数据已随正向迁移 drop）。
如需恢复数据，用删除前导出的 `docspace_docspacedocument.sql`。
"""

from __future__ import annotations

from typing import Any

from django.db import migrations, models

_DOCSPACE_CONFIG_KEYS = ("DOCSPACE_PORTAL_URL", "DOCSPACE_API_TOKEN", "DOCSPACE_ROOT_FOLDER_ID")


def _purge_docspace_configs(apps: Any, schema_editor: Any) -> None:
    SystemConfig = apps.get_model("core", "SystemConfig")
    SystemConfig.objects.filter(
        models.Q(category="docspace") | models.Q(key__in=_DOCSPACE_CONFIG_KEYS)
    ).delete()


def _restore_docspace_category(apps: Any, schema_editor: Any) -> None:
    """反向：把枚举值加回去（数据不恢复）。"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0037_seed_onlyoffice_config"),
    ]

    operations = [
        # 先清数据，再改枚举：避免存量行违反新的 choices
        migrations.RunPython(_purge_docspace_configs, _restore_docspace_category),
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
                    ("general", "通用配置"),
                ],
                default="general",
                help_text="配置项所属分类",
                max_length=50,
                verbose_name="分类",
            ),
        ),
        # 孤儿表：docspace app 已删除，这里显式 drop（幂等：表不存在时跳过）
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS docspace_docspacedocument;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
