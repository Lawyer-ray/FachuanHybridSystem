from django.db import migrations, models


def migrate_other_to_invoice(apps, schema_editor):
    FinalizedMaterial = apps.get_model("contracts", "FinalizedMaterial")
    FinalizedMaterial.objects.filter(category="other").update(category="invoice")


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0005_add_law_firm_oa_case_number"),
    ]

    operations = [
        migrations.RunPython(migrate_other_to_invoice, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="finalizedmaterial",
            name="category",
            field=models.CharField(
                choices=[
                    ("contract_original", "合同正本"),
                    ("supplementary_agreement", "补充协议"),
                    ("invoice", "发票"),
                ],
                default="invoice",
                max_length=32,
                verbose_name="材料分类",
            ),
        ),
    ]
