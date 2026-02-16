from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat_records', '0005_chatrecordrecording_extract_dedup_threshold_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatrecordrecording',
            name='extract_ocr_min_new_chars',
            field=models.IntegerField(blank=True, null=True, verbose_name='OCR 新增字符阈值'),
        ),
        migrations.AddField(
            model_name='chatrecordrecording',
            name='extract_ocr_similarity_threshold',
            field=models.FloatField(blank=True, null=True, verbose_name='OCR 相似度阈值'),
        ),
        migrations.AlterField(
            model_name='chatrecordrecording',
            name='extract_strategy',
            field=models.CharField(choices=[('interval', '固定间隔'), ('scene', '画面变化优先'), ('smart', '智能去重'), ('keyframe', '关键帧(I帧)'), ('ocr', 'OCR 文本变化优先')], default='interval', max_length=16, verbose_name='抽帧策略'),
        ),
    ]
