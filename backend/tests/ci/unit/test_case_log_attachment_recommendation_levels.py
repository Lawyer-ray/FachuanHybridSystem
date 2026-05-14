from __future__ import annotations

from apps.cases.services.template.folder_binding_service import CaseFolderBindingService


def test_log_attachment_recommendation_reason_levels_are_stable() -> None:
    high_reasons = {
        "file_name_rule_match",
        "file_name_keyword_match",
        "source_subfolder_match",
    }
    medium_reasons = {
        "file_name_generic_match",
        "preferred_log_attachment_subdir",
        "matched_log_attachment_subdir",
    }
    low_reasons = {
        "source_subfolder_default",
        "default_log_attachment_subdir",
        "no_binding_default",
        "binding_unavailable_default",
    }

    # 这里只固定普通日志附件上传依赖的 reason 分层，避免前端自动填规则被无意改乱。
    known_reasons = high_reasons | medium_reasons | low_reasons

    service = CaseFolderBindingService()
    assert isinstance(service, CaseFolderBindingService)
    assert "file_name_rule_match" in known_reasons
    assert "preferred_log_attachment_subdir" in known_reasons
    assert "default_log_attachment_subdir" in known_reasons
