from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat_records', '0006_chatrecordrecording_extract_ocr_min_new_chars_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatrecordrecording',
            name='extract_cancel_requested',
            field=models.BooleanField(default=False, verbose_name='请求取消抽帧'),
        ),
    ]
