from __future__ import annotations

from django.apps import AppConfig


class DocWorkspaceConfig(AppConfig):
    """文档工作面：以「项目文件夹里的那一份文件」为坐标的写通道、快照与审查。

    为什么单独一个 app 而不是塞进 `onlyoffice`：`onlyoffice` 只负责「怎么把文件
    交给 DS、怎么把 DS 的回写接回来」，它对业务语义（审查结论、修订决策、版本
    留底）一无所知。把业务写进去会让那个 app 同时承担协议适配与领域逻辑，两边
    都改不动。
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.doc_workspace"
    verbose_name = "文档工作面"
