from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat_records', '0004_chatrecordscreenshot_dhash_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatrecordrecording',
            name='extract_dedup_threshold',
            field=models.IntegerField(blank=True, null=True, verbose_name='抽帧去重阈值'),
        ),
        migrations.AddField(
            model_name='chatrecordrecording',
            name='extract_strategy',
            field=models.CharField(choices=[('interval', '固定间隔'), ('scene', '画面变化优先')], default='interval', max_length=16, verbose_name='抽帧策略'),
        ),
    ]
