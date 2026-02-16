from django.db import migrations, models


def seed_case_filing_number_sequences(apps, schema_editor) -> None:
    """
    数据迁移函数:从 Case 的 filing_number 字段初始化序列

    注意:如果 Case 模型没有 filing_number 字段,此函数将安全跳过
    """
    Case = apps.get_model("cases", "Case")
    Seq = apps.get_model("cases", "CaseFilingNumberSequence")

    # 检查 Case 模型是否有 filing_number 字段
    if not hasattr(Case, 'filing_number'):
        # 字段不存在,跳过数据迁移
        return

    max_by_year: dict[int, int] = {}
    try:
        for filing_number in (
            Case.objects.exclude(filing_number__isnull=True)
            .exclude(filing_number="")
            .values_list("filing_number", flat=True)
        ):
            parts = str(filing_number).split("_")
            if len(parts) < 4:
                continue
            try:
                year = int(parts[0])
                seq = int(parts[-1])
            except (TypeError, ValueError):
                continue
            prev = max_by_year.get(year, 0)
            if seq > prev:
                max_by_year[year] = seq

        for year, max_seq in max_by_year.items():
            Seq.objects.update_or_create(year=year, defaults={"next_value": max_seq + 1})
    except Exception:
        # 如果查询失败(例如字段不存在),安全跳过
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0008_add_case_template_binding"),
    ]

    operations = [
        migrations.CreateModel(
            name="CaseFilingNumberSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.IntegerField(unique=True, verbose_name="年份")),
                ("next_value", models.IntegerField(default=1, verbose_name="下一个序号")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
            ],
        ),
        migrations.RunPython(seed_case_filing_number_sequences, migrations.RunPython.noop),
    ]
