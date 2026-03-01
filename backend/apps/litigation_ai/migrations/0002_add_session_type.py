from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("litigation_ai", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="litigationsession",
            name="session_type",
            field=models.CharField(
                choices=[("doc_gen", "文书生成"), ("mock_trial", "模拟庭审")],
                default="doc_gen",
                help_text="文书生成或模拟庭审",
                max_length=20,
                verbose_name="会话类型",
            ),
        ),
        migrations.AddIndex(
            model_name="litigationsession",
            index=models.Index(fields=["session_type"], name="documents_li_session_8e1f3a_idx"),
        ),
    ]
