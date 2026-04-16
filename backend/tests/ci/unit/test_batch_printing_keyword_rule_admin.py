from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.utils import timezone

from apps.batch_printing.admin.batch_printing_admin import PrintKeywordRuleAdmin
from apps.batch_printing.models import PrintKeywordRule, PrintPresetSnapshot


@pytest.mark.django_db
def test_print_keyword_rule_admin_form_hides_manual_printer_field() -> None:
    admin = PrintKeywordRuleAdmin(PrintKeywordRule, AdminSite())
    request = RequestFactory().get("/admin/batch_printing/printkeywordrule/add/")

    form_class = admin.get_form(request)
    form = form_class()

    assert "printer_name" not in form_class.base_fields
    assert "preset_snapshot" in form.fields
    assert "自动取该预置所属打印机" in (form.fields["preset_snapshot"].help_text or "")


@pytest.mark.django_db
def test_print_keyword_rule_admin_save_model_syncs_printer_name_from_preset() -> None:
    preset = PrintPresetSnapshot.objects.create(
        printer_name="canonprinter",
        printer_display_name="Canon Printer",
        preset_name="双面",
        preset_source="mac_plist",
        raw_settings_payload={},
        executable_options_payload={},
        supported_option_names=[],
        last_synced_at=timezone.now(),
    )
    admin = PrintKeywordRuleAdmin(PrintKeywordRule, AdminSite())
    request = RequestFactory().post("/admin/batch_printing/printkeywordrule/add/")
    rule = PrintKeywordRule(
        keyword="起诉状",
        priority=10,
        enabled=True,
        printer_name="should-be-overwritten",
        preset_snapshot=preset,
    )

    admin.save_model(request, rule, form=None, change=False)
    rule.refresh_from_db()

    assert rule.printer_name == "canonprinter"
