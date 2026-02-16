import pytest


@pytest.mark.django_db
def test_case_admin_form_marks_cause_autocomplete_input():
    from apps.cases.admin.case_forms_admin import CaseAdminForm

    form = CaseAdminForm()
    widget = form.fields["cause_of_action"].widget
    assert "js-cause-autocomplete" in (widget.attrs.get("class") or "")


@pytest.mark.django_db
def test_supervising_authority_inline_form_marks_court_autocomplete_input():
    from apps.cases.admin.case_forms_admin import SupervisingAuthorityInlineForm

    form = SupervisingAuthorityInlineForm()
    widget = form.fields["name"].widget
    assert "js-court-autocomplete" in (widget.attrs.get("class") or "")
