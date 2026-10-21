"""发票识别任务 admin change_form 页面渲染回归测试。

背景（v27.2.15 / PR #523）：清理 automation 遗留模板时删除了
``admin/automation/invoicerecognitiontask/change_form.html``，而
invoice_recognition 侧的 ``change_form.html`` 当时只有一行薄委托
（extends 该旧路径），叠加后 ``/admin/invoice_recognition/invoicerecognitiontask/``
的 add/change 页全部 500（TemplateDoesNotExist）。修复：554 行完整模板
随 app 落位到 invoice_recognition 模板目录。

注：``InvoiceRecognitionTask`` 为 managed=False（表由原始 SQL 维护），
测试库无该表，故只覆盖 add 页渲染（不触发表数据读写）。
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def superuser(db: Any) -> Any:
    from apps.organization.models import Lawyer

    return Lawyer.objects.create_superuser(
        username="invoice_tpl_admin",
        email=None,
        password="testpass1234!",  # pragma: allowlist secret
    )


class TestInvoiceRecognitionChangeFormRender:
    @pytest.mark.django_db
    def test_add_page_renders_custom_template(self, client: Any, superuser: Any) -> None:
        client.force_login(superuser)
        response = client.get("/admin/invoice_recognition/invoicerecognitiontask/add/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        # 自定义模板特征：extrastyle 中的发票上传/合并样式引用（extends 链与 static 引用完整）
        assert "automation/css/invoice_recognition_upload.css" in content
        assert "automation/css/invoice_recognition_merge.css" in content
        # add 页仅展示任务名称字段（get_fields 对新对象的裁剪）
        assert 'name="name"' in content
