from django.apps import AppConfig


class DocVerifyConfig(AppConfig):
    """回传件内容核对。

    **不在此注册任何 signal**：入站钩子由调用方（收件箱/归案）显式投任务，
    避免「谁在什么时候触发了核对」变成隐式行为——那会在排障时不可见。
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.doc_verify"
    verbose_name = "回传件内容核对"
