from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("contracts", "0002_initial"),
        ("cases", "0003_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Reminder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reminder_type", models.CharField(choices=[("hearing", "开庭"), ("asset_preservation_expires", "财产保全到期日"), ("evidence_deadline", "举证到期日"), ("appeal_deadline", "上诉期到期日"), ("statute_limitations", "诉讼时效到期日"), ("payment_deadline", "缴费期限"), ("submission_deadline", "补正/材料提交期限"), ("other", "其他")], max_length=64, verbose_name="类型")),
                ("content", models.CharField(max_length=255, verbose_name="提醒事项")),
                ("due_at", models.DateTimeField(verbose_name="到期时间")),
                ("metadata", models.JSONField(blank=True, default=dict, verbose_name="扩展数据")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("case_log", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="reminders", to="cases.caselog", verbose_name="案件日志")),
                ("contract", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="reminders", to="contracts.contract", verbose_name="合同")),
            ],
            options={
                "verbose_name": "重要日期提醒",
                "verbose_name_plural": "重要日期提醒",
            },
        ),
        migrations.AddConstraint(
            model_name="reminder",
            constraint=models.CheckConstraint(
                condition=models.Q(("contract__isnull", False), ("case_log__isnull", True))
                | models.Q(("contract__isnull", True), ("case_log__isnull", False)),
                name="reminders_reminder_bind_exactly_one",
            ),
        ),
        migrations.AddIndex(
            model_name="reminder",
            index=models.Index(fields=["due_at"], name="reminders_re_due_at_6bbf33_idx"),
        ),
        migrations.AddIndex(
            model_name="reminder",
            index=models.Index(fields=["reminder_type"], name="reminders_re_reminde_86cf4f_idx"),
        ),
        migrations.AddIndex(
            model_name="reminder",
            index=models.Index(fields=["contract"], name="reminders_re_contrac_25f5ba_idx"),
        ),
        migrations.AddIndex(
            model_name="reminder",
            index=models.Index(fields=["case_log"], name="reminders_re_case_lo_eb60b8_idx"),
        ),
    ]
