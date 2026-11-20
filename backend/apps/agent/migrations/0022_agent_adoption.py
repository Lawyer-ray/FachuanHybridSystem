# Generated manually (号已预分配：0022_agent_adoption)
# 只建一张表：律师对某次评审的当前采纳结果（同一 review 一行）。

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0021_agent_review"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentReviewAdoption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "lane",
                    models.CharField(
                        blank=True,
                        default=None,
                        max_length=64,
                        null=True,
                        verbose_name="采纳栏",
                    ),
                ),
                ("merged", models.BooleanField(default=False, verbose_name="合并采纳")),
                ("note", models.CharField(blank=True, default="", max_length=500, verbose_name="备注")),
                ("adopted_at", models.DateTimeField(auto_now=True, verbose_name="采纳时间")),
                (
                    "review",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="adoption",
                        to="agent.agentreview",
                        verbose_name="评审",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="agent_review_adoptions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="采纳人",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agent 评审采纳",
                "verbose_name_plural": "Agent 评审采纳",
            },
        ),
    ]
