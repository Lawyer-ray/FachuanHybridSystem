"""FileField 空值语义归一回归测试。

归一后契约：业务 FileField/ImageField 列级 NOT NULL + ORM 默认空串
（workbench.batch_job 是库内既有范式），创建不传字段落 ''，真值判断
（`if obj.file:`）语义不变。本批覆盖 14 字段/10 app，此处取创建成本
最低的锚点模型各验一条，其余字段同构。
"""

from __future__ import annotations

import pytest

from apps.automation.models import GsxtReportTask
from apps.organization.models import Lawyer
from apps.testing.factories import ClientFactory


@pytest.mark.django_db
class TestFileFieldDefaults:
    def test_lawyer_file_fields_default_empty(self):
        lawyer = Lawyer.objects.create(username="filefield-lawyer")
        lawyer.refresh_from_db()
        assert lawyer.license_pdf == ""
        assert lawyer.avatar == ""
        assert not lawyer.license_pdf
        assert not lawyer.avatar

    def test_lawyer_truthiness_still_works_for_missing_file(self):
        lawyer = Lawyer.objects.create(username="filefield-lawyer-2")
        # signals 与导出逻辑统一走真值判断，'' 与 None 同为 falsy
        assert bool(lawyer.license_pdf) is False

    def test_gsxt_report_file_default_empty(self):
        client = ClientFactory(client_type="legal")
        task = GsxtReportTask.objects.create(client=client, company_name="测试企业")
        task.refresh_from_db()
        assert task.report_file == ""
        assert not task.report_file
