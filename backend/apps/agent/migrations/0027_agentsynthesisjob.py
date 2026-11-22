# 综合结论改为后台任务：新增 AgentSynthesisJob（手写，与 models/synthesis.py 逐字段对应）。

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0026_agentreview_clusters_agentreview_clusters_error_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentSynthesisJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job_id', models.CharField(max_length=32, unique=True, verbose_name='任务标识')),
                ('turn', models.PositiveIntegerField(verbose_name='轮次')),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('queued', '排队中'),
                            ('running', '运行中'),
                            ('succeeded', '已完成'),
                            ('failed', '失败'),
                            ('cancelled', '已取消'),
                        ],
                        default='queued',
                        max_length=16,
                        verbose_name='状态',
                    ),
                ),
                ('stage', models.CharField(blank=True, default='', max_length=16, verbose_name='阶段')),
                ('params', models.JSONField(blank=True, default=dict, verbose_name='参数')),
                ('cancel_requested', models.BooleanField(default=False, verbose_name='已请求取消')),
                ('error', models.CharField(blank=True, default='', max_length=255, verbose_name='失败原因')),
                ('task_id', models.CharField(blank=True, default='', max_length=64, verbose_name='队列任务 ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('started_at', models.DateTimeField(blank=True, null=True, verbose_name='开始时间')),
                ('finished_at', models.DateTimeField(blank=True, null=True, verbose_name='结束时间')),
                (
                    'session',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='synthesis_jobs',
                        to='agent.agentsession',
                        verbose_name='所属会话',
                    ),
                ),
                (
                    'synthesis',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='jobs',
                        to='agent.agentsynthesis',
                        verbose_name='综合结论',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='agent_synthesis_jobs',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='发起人',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Agent 综合结论任务',
                'verbose_name_plural': 'Agent 综合结论任务',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['session', 'turn'], name='agent_synth_job_sess_turn_idx')],
                'constraints': [
                    models.UniqueConstraint(
                        condition=models.Q(('status__in', ['queued', 'running'])),
                        fields=('session', 'turn'),
                        name='agent_synth_job_one_active',
                    )
                ],
            },
        ),
    ]
