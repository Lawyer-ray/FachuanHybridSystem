"""P05-03 回归：重新绑定案件只能软解绑，不得物理删除旧 CaseLog 与附件。

旧实现（`_cleanup_old_case_log`）会 `attachment.file.delete(save=False)` + `old_log.delete()`，
删掉的正文与已归档文书不可恢复。修法：只把 `sms.case_log` 置空，日志与附件保留。
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.automation.models import CourtSMS
from apps.automation.services.sms._sms_case_binding_mixin import SMSCaseBindingMixin
from apps.cases.models import CaseLog, CaseLogAttachment
from apps.testing.factories import CaseLogFactory


def _make_mixin() -> SMSCaseBindingMixin:
    class Concrete(SMSCaseBindingMixin):
        @property
        def case_service(self) -> Any:
            return MagicMock()

        @property
        def lawyer_service(self) -> Any:
            return MagicMock()

    return Concrete()


@pytest.mark.django_db
def test_rebinding_keeps_old_case_log_and_attachments(caplog: Any) -> None:
    """软解绑后：短信不再指向旧日志，旧日志与附件仍在库里。"""
    old_log = CaseLogFactory(content="收到法院短信：原短信内容")
    attachment = CaseLogAttachment.objects.create(
        log=old_log,
        file="case_logs/2026/01/送达回证.pdf",
        original_filename="送达回证.pdf",
    )
    sms = CourtSMS.objects.create(content="重新匹配后的短信", received_at=timezone.now(), case_log=old_log)

    with caplog.at_level(logging.INFO):
        _make_mixin()._unbind_old_case_log(sms)

    sms.refresh_from_db()
    assert sms.case_log_id is None
    assert CaseLog.objects.filter(id=old_log.id).exists()
    assert CaseLogAttachment.objects.filter(id=attachment.id).exists()
    # 日志里必须留一条「已解绑，原 log id=…」便于追溯
    assert f"原 CaseLog ID={old_log.id}" in caplog.text


def test_unbind_never_touches_files_or_deletes_rows() -> None:
    """解绑路径不允许对旧日志调用 delete（软解绑的核心约束）。"""
    mixin = _make_mixin()
    old_log = MagicMock()
    sms = SimpleNamespace(id=1, case_log_id=42, case_log=old_log, save=MagicMock())

    mixin._unbind_old_case_log(sms)

    assert sms.case_log is None
    sms.save.assert_called_once_with(update_fields=["case_log"])
    old_log.delete.assert_not_called()


def test_no_old_case_log_is_noop() -> None:
    """没有旧日志时不做任何写操作。"""
    mixin = _make_mixin()
    sms = SimpleNamespace(id=1, case_log_id=None, save=MagicMock())

    mixin._unbind_old_case_log(sms)

    sms.save.assert_not_called()
