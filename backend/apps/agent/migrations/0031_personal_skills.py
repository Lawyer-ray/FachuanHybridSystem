"""个人技能 P0：新增 AgentSkill / AgentSkillRevision，改造 AgentSkillPreference。

## 为什么手写（自动生成的迁移会丢数据）

``skill_name`` → ``skill_key`` 是**换身份**：现存每一行都是内置技能的偏好，必须
回填成 ``builtin:<name>`` 才能对上随代码发布的那份技能库。``makemigrations``
对「删字段 + 加非空字段」只会生成两步，数据直接丢，所以这里显式六步：

1. ``AddField skill_key``（先给 ``default=""``，否则存量行无法加非空列）
2. ``AlterUniqueTogether`` 清空旧约束 ``(user, skill_name)``
3. ``RunPython`` 回填 ``"builtin:" + skill_name``（反向：剥前缀回填，``skill:`` 行删除）
4. ``RemoveField skill_name``
5. ``AlterField skill_key``（max_length=80，去掉临时 default、不允许空）
6. ``AlterUniqueTogether`` 建 ``(user, skill_key)``

**与 P0-BRIEF 列表的一处顺序差异（有意）**：第 2、3 步互换。反向迁移按操作逆序
执行，若保留 ``RunPython → 清约束 → RemoveField`` 的原顺序，逆序会先重建
``(user, skill_name)`` 唯一约束、再回填 ``skill_name``——多技能用户此时所有行的
``skill_name`` 都是空串，约束当场冲突。先清约束、再回填，正反两向都成立。

## 新增的两张表

``AgentSkill`` 的 team / law_firm 归属字段与两条唯一约束现在就建：将来加团队/
所内技能不改表、不改主键；等有重复数据再补约束要停机清洗。
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_skill_key(apps, schema_editor):
    """所有现存偏好行都是内置技能：``skill_name`` → ``builtin:<name>``。"""
    Preference = apps.get_model("agent", "AgentSkillPreference")
    for preference in Preference.objects.all().iterator():
        preference.skill_key = "builtin:" + preference.skill_name
        preference.save(update_fields=["skill_key"])


def restore_skill_name(apps, schema_editor):
    """反向：``builtin:`` 剥前缀回填；``skill:<uuid>`` 是 P0 之后才有的行，删除。"""
    Preference = apps.get_model("agent", "AgentSkillPreference")
    for preference in Preference.objects.all().iterator():
        if not preference.skill_key.startswith("builtin:"):
            preference.delete()
            continue
        preference.skill_name = preference.skill_key[len("builtin:") :]
        preference.save(update_fields=["skill_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("agent", "0030_uiaction_unsettled_unique"),
        ("organization", "0012_lawfirm_name_unique"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentSkill",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "scope",
                    models.CharField(
                        choices=[("lawyer", "个人"), ("team", "团队"), ("law_firm", "所内")],
                        default="lawyer",
                        max_length=16,
                    ),
                ),
                ("name", models.CharField(max_length=64, verbose_name="技能名")),
                ("title", models.CharField(max_length=64, verbose_name="显示名")),
                ("description", models.CharField(max_length=400, verbose_name="路由描述")),
                ("body", models.TextField(verbose_name="正文")),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "草稿"), ("active", "生效"), ("archived", "已下线")],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("enabled", models.BooleanField(default=True, verbose_name="启用")),
                ("source", models.CharField(default="manual", max_length=16, verbose_name="来源")),
                ("version", models.PositiveIntegerField(default=1, verbose_name="版本")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="创建人",
                    ),
                ),
                (
                    "law_firm",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_skills",
                        to="organization.lawfirm",
                        verbose_name="所属律所",
                    ),
                ),
                (
                    "lawyer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_skills",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="所属律师",
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_skills",
                        to="organization.team",
                        verbose_name="所属团队",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agent 技能",
                "verbose_name_plural": "Agent 技能",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="AgentSkillRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version", models.PositiveIntegerField()),
                ("title", models.CharField(max_length=64)),
                ("description", models.CharField(max_length=400)),
                ("body", models.TextField()),
                ("status", models.CharField(max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "edited_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "skill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="revisions",
                        to="agent.agentskill",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agent 技能版本",
                "verbose_name_plural": "Agent 技能版本",
                "ordering": ["-version"],
            },
        ),
        migrations.AddIndex(
            model_name="agentskill",
            index=models.Index(fields=["scope", "law_firm", "status"], name="agent_skill_firm_status_idx"),
        ),
        migrations.AddIndex(
            model_name="agentskill",
            index=models.Index(fields=["team", "status"], name="agent_skill_team_status_idx"),
        ),
        migrations.AddIndex(
            model_name="agentskill",
            index=models.Index(fields=["lawyer", "enabled"], name="agent_skill_lawyer_enabled_idx"),
        ),
        migrations.AddConstraint(
            model_name="agentskill",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("law_firm__isnull", True),
                        ("lawyer__isnull", False),
                        ("scope", "lawyer"),
                        ("team__isnull", True),
                    ),
                    models.Q(
                        ("law_firm__isnull", True),
                        ("lawyer__isnull", True),
                        ("scope", "team"),
                        ("team__isnull", False),
                    ),
                    models.Q(
                        ("law_firm__isnull", False),
                        ("lawyer__isnull", True),
                        ("scope", "law_firm"),
                        ("team__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="agent_skill_scope_owner_consistent",
            ),
        ),
        migrations.AddConstraint(
            model_name="agentskill",
            constraint=models.UniqueConstraint(
                condition=models.Q(("lawyer__isnull", False)),
                fields=("lawyer", "name"),
                name="uniq_agent_skill_lawyer_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="agentskill",
            constraint=models.UniqueConstraint(
                condition=models.Q(("team__isnull", False)),
                fields=("team", "name"),
                name="uniq_agent_skill_team_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="agentskill",
            constraint=models.UniqueConstraint(
                condition=models.Q(("law_firm__isnull", False)),
                fields=("law_firm", "name"),
                name="uniq_agent_skill_firm_name",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="agentskillrevision",
            unique_together={("skill", "version")},
        ),
        migrations.AddField(
            model_name="agentskillpreference",
            name="skill_key",
            field=models.CharField(default="", max_length=80, verbose_name="技能键"),
        ),
        migrations.AlterUniqueTogether(
            name="agentskillpreference",
            unique_together=set(),
        ),
        migrations.RunPython(backfill_skill_key, restore_skill_name),
        # 反向安全阀（不是笔误）：RemoveField 的逆向是 AddField，字段定义取自**上一步
        # 的迁移状态**。0014 里 ``skill_name`` 是 ``blank=False``、无默认值，Django 会生成
        # ``ADD COLUMN ... NOT NULL``（无 DEFAULT）——空表能过，表里有偏好行时直接
        # NotNullViolation，反向迁移整体失败。这里先把字段状态改成 ``blank=True,
        # default=""``：迁移状态变了、实际 DDL 不变（Django 不在库里建 DEFAULT），
        # 反向 AddField 于是带 ``DEFAULT ''``，随后 RunPython 回填、再重建唯一约束。
        migrations.AlterField(
            model_name="agentskillpreference",
            name="skill_name",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="技能名"),
        ),
        migrations.RemoveField(
            model_name="agentskillpreference",
            name="skill_name",
        ),
        migrations.AlterField(
            model_name="agentskillpreference",
            name="skill_key",
            field=models.CharField(max_length=80, verbose_name="技能键"),
        ),
        migrations.AlterUniqueTogether(
            name="agentskillpreference",
            unique_together={("user", "skill_key")},
        ),
    ]
