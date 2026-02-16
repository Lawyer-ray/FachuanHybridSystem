import uuid

import apps.chat_records.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("organization", "0003_alter_lawyer_license_pdf"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatRecordProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="项目名称")),
                ("description", models.TextField(blank=True, verbose_name="说明")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="chat_record_projects",
                        to="organization.lawyer",
                        verbose_name="创建人",
                    ),
                ),
            ],
            options={
                "verbose_name": "梳理聊天记录",
                "verbose_name_plural": "梳理聊天记录",
            },
        ),
        migrations.CreateModel(
            name="ChatRecordExportTask",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("export_type", models.CharField(choices=[("pdf", "PDF"), ("docx", "Word")], max_length=16, verbose_name="导出类型")),
                ("layout", models.JSONField(blank=True, default=dict, verbose_name="版式配置")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "待处理"), ("running", "处理中"), ("success", "成功"), ("failed", "失败")],
                        default="pending",
                        max_length=16,
                        verbose_name="状态",
                    ),
                ),
                ("progress", models.PositiveIntegerField(default=0, verbose_name="进度百分比")),
                ("current", models.PositiveIntegerField(default=0, verbose_name="当前项")),
                ("total", models.PositiveIntegerField(default=0, verbose_name="总项")),
                ("message", models.CharField(blank=True, max_length=255, verbose_name="进度信息")),
                ("error", models.TextField(blank=True, verbose_name="错误信息")),
                ("output_file", models.FileField(blank=True, null=True, upload_to=apps.chat_records.models._export_upload_to, verbose_name="导出文件")),
                ("started_at", models.DateTimeField(blank=True, null=True, verbose_name="开始时间")),
                ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="完成时间")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="export_tasks",
                        to="chat_records.chatrecordproject",
                        verbose_name="项目",
                    ),
                ),
            ],
            options={
                "verbose_name": "聊天记录导出任务",
                "verbose_name_plural": "聊天记录导出任务",
            },
        ),
        migrations.CreateModel(
            name="ChatRecordScreenshot",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("image", models.ImageField(upload_to=apps.chat_records.models._screenshot_upload_to, verbose_name="截图")),
                ("ordering", models.PositiveIntegerField(default=0, verbose_name="顺序")),
                ("title", models.CharField(blank=True, max_length=255, verbose_name="标题")),
                ("note", models.TextField(blank=True, verbose_name="备注")),
                ("sha256", models.CharField(blank=True, db_index=True, max_length=64, verbose_name="内容哈希")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="screenshots",
                        to="chat_records.chatrecordproject",
                        verbose_name="项目",
                    ),
                ),
            ],
            options={
                "verbose_name": "聊天记录截图",
                "verbose_name_plural": "聊天记录截图",
                "ordering": ["ordering", "created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="chatrecordproject",
            index=models.Index(fields=["-created_at"], name="chat_records_created_8f2b09_idx"),
        ),
        migrations.AddIndex(
            model_name="chatrecordproject",
            index=models.Index(fields=["created_by"], name="chat_records_created_5efc36_idx"),
        ),
        migrations.AddIndex(
            model_name="chatrecordscreenshot",
            index=models.Index(fields=["project", "ordering"], name="chat_records_project_f631f7_idx"),
        ),
        migrations.AddIndex(
            model_name="chatrecordscreenshot",
            index=models.Index(fields=["project", "-created_at"], name="chat_records_project_4bb0d8_idx"),
        ),
        migrations.AddIndex(
            model_name="chatrecordexporttask",
            index=models.Index(fields=["project", "-created_at"], name="chat_records_project_7f5b5c_idx"),
        ),
        migrations.AddIndex(
            model_name="chatrecordexporttask",
            index=models.Index(fields=["status", "-created_at"], name="chat_records_status_ae07c5_idx"),
        ),
    ]
