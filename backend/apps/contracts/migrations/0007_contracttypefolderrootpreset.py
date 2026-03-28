from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0006_finalized_material_invoice_category"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContractTypeFolderRootPreset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "case_type",
                    models.CharField(
                        choices=[
                            ("civil", "民商事"),
                            ("criminal", "刑事"),
                            ("administrative", "行政"),
                            ("labor", "劳动仲裁"),
                            ("intl", "商事仲裁"),
                            ("special", "专项服务"),
                            ("advisor", "常法顾问"),
                        ],
                        max_length=32,
                        unique=True,
                        verbose_name="合同类型",
                    ),
                ),
                (
                    "root_path",
                    models.CharField(
                        help_text="该合同类型下用于自动匹配的根目录",
                        max_length=1000,
                        verbose_name="根目录",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
            ],
            options={
                "verbose_name": "合同类型根目录预设",
                "verbose_name_plural": "合同类型根目录预设",
            },
        ),
        migrations.AddIndex(
            model_name="contracttypefolderrootpreset",
            index=models.Index(fields=["case_type"], name="contracts_c_case_ty_88f56d_idx"),
        ),
    ]
