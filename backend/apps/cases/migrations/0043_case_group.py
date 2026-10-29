from django.db import migrations, models


class Migration(migrations.Migration):
    """Case 加案组字段（系列案 / 一案多审级分组）。

    为什么用 group_key 字符串而不是 FK 建 CaseGroup 表：
      绝大多数委托只有一桩事儿，建表+关联会让每次建案都要先建组，成本大于收益。
      group_key 是「同 key 即同组」的约定，单案场景留空即可。
      将来若要升级成实体表，可用 group_key 做数据迁移来源，不会白做。

    HistoricalCase 也要同步加：
      Case 有 HistoricalRecords()，历史表缺字段会让历史查询直接报错。
    """

    dependencies = [
        ("cases", "0042_case_yz_wid"),
    ]

    operations = [
        migrations.AddField(
            model_name="case",
            name="group_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="同 key 视为同一案组（一案多审级、系列案）。单案留空。",
                max_length=64,
                verbose_name="案组标识",
            ),
        ),
        migrations.AddField(
            model_name="historicalcase",
            name="group_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="同 key 视为同一案组（一案多审级、系列案）。单案留空。",
                max_length=64,
                verbose_name="案组标识",
            ),
        ),
        migrations.AddField(
            model_name="case",
            name="group_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="系列案时的子案名，如「某某诉某某买卖合同纠纷」；单案留空。",
                max_length=255,
                verbose_name="案组名称",
            ),
        ),
        migrations.AddField(
            model_name="historicalcase",
            name="group_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="系列案时的子案名，如「某某诉某某买卖合同纠纷」；单案留空。",
                max_length=255,
                verbose_name="案组名称",
            ),
        ),
    ]
