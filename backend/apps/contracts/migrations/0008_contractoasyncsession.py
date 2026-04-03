from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0002_remove_is_preferred"),
        ("contracts", "0007_contracttypefolderrootpreset"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContractOASyncSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "待执行"),
                            ("running", "执行中"),
                            ("completed", "已完成"),
                            ("failed", "失败"),
                            ("cancelled", "已取消"),
                        ],
                        default="pending",
                        max_length=16,
                        verbose_name="状态",
                    ),
                ),
                ("task_id", models.CharField(blank=True, default="", max_length=64, verbose_name="DjangoQ任务ID")),
                ("total_count", models.PositiveIntegerField(default=0, verbose_name="总数")),
                ("processed_count", models.PositiveIntegerField(default=0, verbose_name="已处理")),
                ("matched_count", models.PositiveIntegerField(default=0, verbose_name="唯一命中")),
                ("multiple_count", models.PositiveIntegerField(default=0, verbose_name="多结果")),
                ("not_found_count", models.PositiveIntegerField(default=0, verbose_name="未匹配")),
                ("error_count", models.PositiveIntegerField(default=0, verbose_name="错误")),
                ("progress_message", models.CharField(blank=True, default="", max_length=255, verbose_name="进度信息")),
                ("result_payload", models.JSONField(blank=True, default=dict, verbose_name="结果载荷")),
                ("error_message", models.TextField(blank=True, default="", verbose_name="错误信息")),
                ("started_at", models.DateTimeField(blank=True, null=True, verbose_name="开始时间")),
                ("completed_at", models.DateTimeField(blank=True, null=True, verbose_name="完成时间")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                (
                    "started_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="contract_oa_sync_sessions",
                        to="organization.lawyer",
                        verbose_name="发起人",
                    ),
                ),
            ],
            options={
                "verbose_name": "合同OA同步会话",
                "verbose_name_plural": "合同OA同步会话",
            },
        ),
        migrations.AddIndex(
            model_name="contractoasyncsession",
            index=models.Index(fields=["status", "-created_at"], name="contracts_c_status_3c4e2f_idx"),
        ),
        migrations.AddIndex(
            model_name="contractoasyncsession",
            index=models.Index(fields=["started_by", "-created_at"], name="contracts_c_started_72dffa_idx"),
        ),
    ]
