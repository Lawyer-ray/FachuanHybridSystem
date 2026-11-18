"""AgentMessage 增加 agent_kind（双 agent 并行回答的落库归因）。

## 历史数据为什么回填空串而不是 ``pi``

引入双答之前本系统只有 pi 在跑，把历史行填成 ``pi`` 看着「更完整」，但它是一次
**猜**：这期间的会话也可能由任务式 / 子任务路径产生，将来接入更多后端时无法
区分「确实是 pi」与「当时没这个概念」。空串如实表达「旧数据 / 未标注」，
渲染侧把空串当 pi 即可——信息损失为零，却不会把猜测固化成事实。

## 为什么加 ``db_index``

会话历史回放（``GET /sessions/{id}/messages``）与按栏过滤都要按它筛；
字段取值只有几个短 kind，索引代价可忽略。
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0016_agent_session_agent_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentmessage",
            name="agent_kind",
            field=models.CharField(blank=True, db_index=True, default="", max_length=32, verbose_name="Agent 后端"),
        ),
    ]
