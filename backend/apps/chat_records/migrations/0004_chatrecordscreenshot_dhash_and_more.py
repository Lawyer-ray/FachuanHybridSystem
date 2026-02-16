from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat_records', '0003_chatrecordscreenshot_capture_time_seconds'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatrecordscreenshot',
            name='dhash',
            field=models.CharField(blank=True, db_index=True, max_length=16, verbose_name='感知哈希'),
        ),
        migrations.AddField(
            model_name='chatrecordscreenshot',
            name='frame_score',
            field=models.FloatField(blank=True, null=True, verbose_name='帧评分'),
        ),
        migrations.AddField(
            model_name='chatrecordscreenshot',
            name='is_filtered',
            field=models.BooleanField(default=False, verbose_name='已过滤'),
        ),
        migrations.AddField(
            model_name='chatrecordscreenshot',
            name='source',
            field=models.CharField(choices=[('unknown', '未知'), ('extract', '视频抽帧'), ('upload', '手动上传')], default='unknown', max_length=16, verbose_name='来源'),
        ),
        migrations.AddIndex(
            model_name='chatrecordscreenshot',
            index=models.Index(fields=['project', 'dhash'], name='chat_record_project_9ea8f6_idx'),
        ),
    ]
