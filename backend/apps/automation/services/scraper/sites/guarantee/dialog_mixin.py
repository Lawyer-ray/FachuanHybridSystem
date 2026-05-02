"""gTwo 当事人/代理人/财产线索对话框填写。

Facade: 继承所有子 Mixin，仅保留主编排方法 _complete_g_two。
"""

from __future__ import annotations

import logging
from typing import Any

from .dialog_field_filling import GuaranteeDialogFieldFillingMixin
from .dialog_playwright_fill import GuaranteeDialogPlaywrightFillMixin
from .dialog_property_clue import GuaranteeDialogPropertyClueMixin
from .dialog_ui_helpers import GuaranteeDialogUIHelpersMixin

logger = logging.getLogger("apps.automation")


class GuaranteeDialogMixin(
    GuaranteeDialogFieldFillingMixin,
    GuaranteeDialogPlaywrightFillMixin,
    GuaranteeDialogPropertyClueMixin,
    GuaranteeDialogUIHelpersMixin,
):
    """gTwo 当事人/代理人/财产线索对话框填写。"""

    page: Any
    _api_error_log: list[dict[str, Any]]
    MAX_SLOW_WAIT_MS: int

    def _complete_g_two(self, case_data: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {"dialogs": [], "next_clicked": None, "errors_after_next": [], "ready": False}
        result["ready"] = self._wait_for_g_two_ready()

        self._clear_g_two_existing_data(result)

        respondent_sources = [item for item in (case_data.get("respondents") or []) if isinstance(item, dict)]
        if not respondent_sources:
            respondent_sources = [case_data.get("respondent") or {}]

        property_clue_sources = [item for item in (case_data.get("property_clues") or []) if isinstance(item, dict)]
        if not property_clue_sources and isinstance(case_data.get("property_clue"), dict):
            property_clue_sources = [case_data.get("property_clue") or {}]

        targets = [
            ("applicant", 0, ["申请人"], self._build_party_dialog_defaults(case_data.get("applicant") or {})),  # type: ignore[attr-defined]
            *[
                ("respondent", 1, ["被申请人"], self._build_party_dialog_defaults(source))  # type: ignore[attr-defined]
                for source in respondent_sources
            ],
            (
                "plaintiff_agent",
                2,
                ["原告代理人", "代理人"],
                self._build_agent_dialog_defaults(case_data.get("plaintiff_agent") or case_data.get("applicant") or {}),  # type: ignore[attr-defined]
            ),
            *[
                (
                    "property_clue",
                    3,
                    ["财产线索", "财产"],
                    self._build_party_dialog_defaults(  # type: ignore[attr-defined]
                        case_data.get("respondent") or case_data.get("applicant") or {},
                        is_property_clue=True,
                        property_clue_data=property_clue_source,
                    ),
                )
                for property_clue_source in property_clue_sources
            ],
        ]

        for target, index, section_keywords, defaults in targets:
            step: dict[str, Any] = {
                "target": target,
                "opened": False,
                "filled": [],
                "saved": None,
                "errors": [],
                "cancelled": False,
            }
            opened = False
            for _ in range(3):
                opened = self._click_add_button(index)
                if not opened:
                    opened = self._click_add_button_by_section_keywords(section_keywords)
                if opened:
                    break
                self._random_wait(0.5, 0.8)  # type: ignore[attr-defined]

            step["opened"] = opened
            if not opened:
                result["dialogs"].append(step)
                continue

            row_count_before = self.page.evaluate(r"""() => {
                return document.querySelectorAll('.el-table__body-wrapper .el-table__row').length;
            }""")
            step["table_row_count_before"] = row_count_before

            self._random_wait(0.8, 1.2)  # type: ignore[attr-defined]
            if target in {"applicant", "respondent"}:
                step["party_type_selected"] = self._choose_party_type_in_dialog(defaults)
            selected = self._fill_dialog_select_fields(defaults, target)
            dated = self._fill_dialog_date_fields()
            filled = self._fill_dialog_required_fields(defaults)
            playwright_filled = self._fill_dialog_fields_with_playwright(defaults, target)
            step["filled"] = [*selected, *dated, *filled, *playwright_filled]
            step["saved"] = self._click_first_enabled_button(["确定", "保存", "提交", "完成"])  # type: ignore[attr-defined]
            self._random_wait(0.8, 1.2)  # type: ignore[attr-defined]

            dialog_still_open = self.page.evaluate(r"""() => {
                const layer = document.querySelector('#addSQR');
                if (!layer) return false;
                const st = window.getComputedStyle(layer);
                return st.display !== 'none' && st.visibility !== 'hidden';
            }""")
            step["dialog_closed"] = not dialog_still_open

            row_count_after = self.page.evaluate(r"""() => {
                return document.querySelectorAll('.el-table__body-wrapper .el-table__row').length;
            }""")
            step["table_row_count_after"] = row_count_after

            errors = self._get_visible_form_errors()  # type: ignore[attr-defined]
            if target == "property_clue" and any(
                ("请选择省份" in err) or ("请选择财产所有人" in err) for err in errors
            ):
                step["property_clue_retry"] = self._retry_property_clue_save_on_province_error(defaults)
                self._random_wait(0.5, 0.8)  # type: ignore[attr-defined]
                errors = self._get_visible_form_errors()  # type: ignore[attr-defined]

            step["errors"] = errors
            if errors:
                step["cancelled"] = bool(self._click_first_enabled_button(["取消", "关闭", "返回"]))  # type: ignore[attr-defined]
                self._random_wait(0.6, 0.9)  # type: ignore[attr-defined]

            result["dialogs"].append(step)

        result["next_clicked"] = self._click_first_enabled_button(["下一步", "保存并下一步"])  # type: ignore[attr-defined]
        self._random_wait(2, 3)  # type: ignore[attr-defined]
        result["errors_after_next"] = self._get_visible_form_errors()  # type: ignore[attr-defined]

        if any("数据库保存时失败" in err for err in result["errors_after_next"]):
            api_errors = self.page.evaluate(r"""() => {
                const errs = [];
                document.querySelectorAll('.el-message').forEach(el => {
                    const text = (el.innerText || '').trim();
                    if (text) errs.push(text);
                });
                document.querySelectorAll('.el-notification__content').forEach(el => {
                    const text = (el.innerText || '').trim();
                    if (text) errs.push('NOTIFY: ' + text);
                });
                return errs;
            }""")
            result["api_error_details"] = api_errors
            logger.info(f"gTwo next API errors: {api_errors}")

            result["api_error_log"] = self._api_error_log[-5:] if self._api_error_log else []

            for retry_idx in range(3):
                self._close_popovers()  # type: ignore[attr-defined]
                self._random_wait(1.5, 2.5)  # type: ignore[attr-defined]
                self._click_first_enabled_button(["下一步", "保存并下一步"])  # type: ignore[attr-defined]
                self._random_wait(2, 3)  # type: ignore[attr-defined]
                retry_errors = self._get_visible_form_errors()  # type: ignore[attr-defined]
                result.setdefault("retry_errors", []).append(retry_errors)
                if not any("数据库保存时失败" in err for err in retry_errors):
                    result["errors_after_next"] = retry_errors
                    break
                if "gTwo" in self.page.url:
                    logger.info(f"gTwo数据库保存重试{retry_idx + 1}仍失败，检查表格数据")
                    table_check = self.page.evaluate(r"""() => {
                        const rows = document.querySelectorAll('.el-table__body-wrapper .el-table__row');
                        return {
                            rowCount: rows.length,
                            texts: [...rows].map(r => r.textContent.trim().substring(0, 100))
                        };
                    }""")
                    result.setdefault("table_checks", []).append(table_check)

        return result
