from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0003_initial"),
        ("document_recognition", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="documentrecognitiontask",
            options={
                "managed": True,
                "ordering": ["-created_at"],
                "verbose_name": "文书识别任务",
                "verbose_name_plural": "文书识别任务",
            },
        ),
        # 该表由 automation 应用的原始 SQL 迁移创建，case/case_log 两列已存在。
        # 这里仅把这些 FK 登记进 document_recognition 的迁移图谱（状态级），
        # 使模型与图谱一致，同时避免对真实表发出冲突的 AddField DDL。
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="documentrecognitiontask",
                    name="case",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recognition_tasks",
                        to="cases.case",
                        verbose_name="关联案件",
                    ),
                ),
                migrations.AddField(
                    model_name="documentrecognitiontask",
                    name="case_log",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recognition_tasks",
                        to="cases.caselog",
                        verbose_name="案件日志",
                    ),
                ),
            ],
            # 不执行任何数据库操作（列已由 automation 迁移创建）
            database_operations=[],
        ),
    ]
