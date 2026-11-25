"""记录「保存被丢弃」这一事实，供前端把它说出来。

背景：过期画布的保存会被主动丢弃（`callback_service.stale_canvas_reason`），
但应答仍是 `{"error": 0}`（否则 DS 无限重试同一份旧内容）。于是律师侧
「保存成功」的提示与「内容没落盘」的事实互相矛盾——这条迁移把该事实落库，
让 `GET /onlyoffice/canvas-state` 能把它读出来。
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("onlyoffice", "0005_add_pending_save_as_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="editorsession",
            name="last_save_dropped_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="最近一次被丢弃的保存时间（过期画布，内容未落盘）",
            ),
        ),
    ]
