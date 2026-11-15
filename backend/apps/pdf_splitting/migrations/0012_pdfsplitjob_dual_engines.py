from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pdf_splitting', '0011_pdfsplitjob_stage'),
    ]

    operations = [
        migrations.AddField(
            model_name='pdfsplitjob',
            name='dual_engines',
            field=models.CharField(blank=True, default='', max_length=128, verbose_name='交叉比对引擎'),
        ),
    ]
