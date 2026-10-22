"""AI 平台新增「开启思考模式」开关。

历史实现无条件下发 ``chat_template_kwargs.thinking=false``，导致经网关转发的
推理模型（kimi26 → DeepSeek 等）永远不思考。本迁移只加字段，默认 ``False``
保持既有行为不变；需要深度思考时在 Admin 勾选即可。
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0033_causeofaction_core_cause_name_trgm_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmprovider",
            name="enable_thinking",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "仅对推理模型（如 kimi-2.6 / DeepSeek R1 / MiMo）生效。"
                    "关闭（默认）时下发 chat_template_kwargs.thinking=false，直接作答不思考；"
                    "开启后下发 thinking=true，模型先输出推理过程再作答（延迟与 token 消耗更高）。"
                ),
                verbose_name="开启思考模式",
            ),
        ),
    ]
