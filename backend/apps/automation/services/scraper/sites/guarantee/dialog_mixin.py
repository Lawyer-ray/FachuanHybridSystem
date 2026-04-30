"""gTwo 当事人/代理人/财产线索对话框填写。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("apps.automation")


class GuaranteeDialogMixin:
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

    def _clear_g_two_existing_data(self, result: dict[str, Any]) -> None:
        try:
            existing_rows = self.page.evaluate(r"""() => {
                const rows = document.querySelectorAll('.el-table__body-wrapper .el-table__row');
                return rows.length;
            }""")
            result["existing_rows_before_clear"] = existing_rows
            if existing_rows == 0:
                return

            logger.info(f"gTwo已有{existing_rows}行数据，尝试清理")

            for _ in range(existing_rows + 2):
                delete_btn = (
                    self.page.locator(
                        ".el-table__body-wrapper .el-table__row button, "
                        ".el-table__body-wrapper .el-table__row .el-button"
                    )
                    .filter(has_text="删除")
                    .first
                )
                if delete_btn.count() == 0:
                    break
                try:
                    if delete_btn.is_visible():
                        delete_btn.click(timeout=3000)
                        self._random_wait(0.3, 0.5)  # type: ignore[attr-defined]
                        confirm = self.page.locator(".el-message-box__btns .el-button--primary")
                        if confirm.count() > 0 and confirm.first.is_visible():
                            confirm.first.click(timeout=3000)
                        self._random_wait(0.3, 0.5)  # type: ignore[attr-defined]
                except Exception:
                    break

            remaining = self.page.evaluate(r"""() => {
                return document.querySelectorAll('.el-table__body-wrapper .el-table__row').length;
            }""")
            result["existing_rows_after_clear"] = remaining
            logger.info(f"gTwo数据清理完成，剩余{remaining}行")

        except Exception as exc:
            logger.info(f"gTwo数据清理异常（非致命）: {exc}")

    def _wait_for_g_two_ready(self, retries: int = 12) -> bool:
        for _ in range(retries):
            if "gTwo" not in self.page.url:
                self._random_wait(0.3, 0.5)  # type: ignore[attr-defined]
                continue
            if self.page.locator("xpath=//*[contains(normalize-space(text()),'添加')]").count() > 0:
                return True
            self._random_wait(0.4, 0.7)  # type: ignore[attr-defined]
        return "gTwo" in self.page.url

    def _click_add_button(self, index: int) -> bool:
        add_buttons = self.page.locator("xpath=//*[contains(normalize-space(text()),'添加')]")
        visible_indices: list[int] = []
        for i in range(add_buttons.count()):
            candidate = add_buttons.nth(i)
            try:
                if candidate.is_visible():
                    visible_indices.append(i)
            except Exception:
                continue

        if len(visible_indices) <= index:
            return False

        button = add_buttons.nth(visible_indices[index])
        try:
            button.click(timeout=3000)
            return True
        except Exception:
            try:
                button.click(force=True, timeout=3000)
                return True
            except Exception:
                return False

    def _click_add_button_by_section_keywords(self, keywords: list[str]) -> bool:
        clicked = self.page.evaluate(
            r"""(keys) => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const st = window.getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 1 && r.height > 1;
                };

                const findAddIn = (root) => {
                    if (!root) return null;
                    const nodes = [...root.querySelectorAll('button, [role="button"], .el-button, a, span, div')]
                        .filter((el) => isVisible(el) && (el.innerText || '').replace(/\s+/g, ' ').trim() === '添加');
                    return nodes.length > 0 ? nodes[0] : null;
                };

                for (const key of (keys || [])) {
                    const matches = [...document.querySelectorAll('body *')]
                        .filter((el) => isVisible(el) && (el.innerText || '').replace(/\s+/g, ' ').includes(key));
                    for (const node of matches) {
                        let current = node;
                        for (let i = 0; i < 6 && current; i += 1) {
                            const addBtn = findAddIn(current);
                            if (addBtn) {
                                addBtn.click();
                                return true;
                            }
                            current = current.parentElement;
                        }
                    }
                }
                return false;
            }""",
            keywords,
        )
        return bool(clicked)

    def _choose_party_type_in_dialog(self, defaults: dict[str, str]) -> bool:
        party_type = self._normalize_party_type(defaults.get("party_type") or "natural")  # type: ignore[attr-defined]
        type_text_map = {
            "natural": "自然人",
            "legal": "法人",
            "non_legal_org": "非法人组织",
        }
        target_text = type_text_map.get(party_type, "法人")

        clicked = self.page.evaluate(
            r"""(target) => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const st = window.getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 1 && r.height > 1;
                };
                const dialog = [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper,.fd-com-layer,#addSQR')]
                    .filter(isVisible)
                    .slice(-1)[0] || document;

                const radios = [...dialog.querySelectorAll('label, .el-radio, .el-radio__label, span, div')]
                    .filter((el) => isVisible(el) && (el.innerText || '').replace(/\s+/g, ' ').trim() === target);
                if (radios.length === 0) return false;
                radios[0].click();
                return true;
            }""",
            target_text,
        )
        self._random_wait(0.2, 0.4)  # type: ignore[attr-defined]
        return bool(clicked)

    def _fill_dialog_select_fields(self, defaults: dict[str, str], target: str | None = None) -> list[str]:
        updates = self.page.evaluate(
            r"""(args) => {
                const defaults = args.defaults || {};
                const target = args.target || '';
                const result = [];
                const isVisible = (el) => {
                    if (!el) return false;
                    const st = window.getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 1 && r.height > 1;
                };

                const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
                const pickOption = (preferred) => {
                    const options = [...document.querySelectorAll('.el-select-dropdown__item, .el-option, [role="option"]')]
                        .filter((el) => isVisible(el) && !el.classList.contains('is-disabled'));
                    if (options.length === 0) return '';
                    let targetOption = null;
                    if (preferred) {
                        targetOption = options.find((el) => norm(el.innerText).includes(preferred));
                    }
                    if (!targetOption) targetOption = options.find((el) => norm(el.innerText));
                    if (!targetOption) return '';
                    const text = norm(targetOption.innerText);
                    targetOption.click();
                    return text;
                };

                const dialog = [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper,.fd-com-layer,#addSQR')]
                    .filter(isVisible)
                    .slice(-1)[0] || document;
                const items = [...dialog.querySelectorAll('.el-form-item')].filter(isVisible);

                for (const item of items) {
                    const label = norm(item.querySelector('.el-form-item__label')?.innerText || '');

                    if (label.includes('所属原告')) {
                        const checks = [...item.querySelectorAll('label, .el-checkbox, .el-checkbox__label, span, div')]
                            .filter((el) => isVisible(el) && norm(el.innerText));
                        const unchecked = checks.find((el) => {
                            const checkbox = el.querySelector('input[type="checkbox"]');
                            return checkbox ? !checkbox.checked : true;
                        });
                        if (unchecked) {
                            unchecked.click();
                            result.push(`${label}=已选`);
                        }
                        continue;
                    }

                    if (label.includes('性别')) {
                        const male = [...item.querySelectorAll('label, span, div')]
                            .find((el) => isVisible(el) && norm(el.innerText) === (defaults.gender || '男性'));
                        if (male) {
                            male.click();
                            result.push(`${label}=${defaults.gender || '男性'}`);
                        }
                    }

                    const hasSelect = !!item.querySelector('.el-select, .el-cascader, .fd-sf');
                    if (!hasSelect) continue;

                    const input = item.querySelector('input.el-input__inner');
                    if (!input || input.disabled) continue;

                    const normalizedPartyType = norm(defaults.party_type || '').toLowerCase();
                    const isLegalLike = ['legal', 'non_legal_org', 'nonlegal', 'non_legal', 'non-legal-org'].includes(normalizedPartyType);
                    const forceEnterpriseUnitNature = label.includes('单位性质') && target === 'applicant' && isLegalLike;

                    if (input.value && !label.includes('房产坐落位置') && !forceEnterpriseUnitNature) continue;

                    input.click();
                    let prefer = '';
                    if (label.includes('申请人') || label.includes('被申请人')) {
                        prefer = defaults.name || '';
                    }
                    if (label.includes('财产所有人')) {
                        prefer = defaults.owner_name || defaults.name || '';
                    }
                    if (label.includes('代理人类型')) {
                        prefer = defaults.agent_type || '执业律师';
                    }
                    if (label.includes('单位性质')) {
                        prefer = forceEnterpriseUnitNature ? '企业' : (defaults.unit_nature || '企业');
                    }
                    if (label.includes('财产类型')) {
                        prefer = defaults.property_type || '其他';
                    }
                    if (label.includes('房产坐落位置')) {
                        prefer = (defaults.property_province || '广东省').replace('省', '');
                    }

                    const selected = pickOption(prefer);
                    if (selected) result.push(`${label || 'select'}=${selected}`);
                }

                return result;
            }""",
            {"defaults": defaults, "target": target or ""},
        )
        self._random_wait(0.2, 0.4)  # type: ignore[attr-defined]
        self._close_popovers()  # type: ignore[attr-defined]
        return [str(item) for item in updates]

    def _fill_dialog_date_fields(self) -> list[str]:
        updates = self.page.evaluate(
            r"""() => {
                const result = [];
                const isVisible = (el) => {
                    if (!el) return false;
                    const st = window.getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 1 && r.height > 1;
                };
                const setValue = (input, value) => {
                    input.focus();
                    input.value = value;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.dispatchEvent(new Event('blur', { bubbles: true }));
                    input.blur();
                };
                const dateMap = [
                    ['开始日期', '2020-01-01'],
                    ['结束日期', '2099-12-31'],
                    ['选择日期', '1990-01-01'],
                ];
                const dialog = [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper,.fd-com-layer,#addSQR')]
                    .filter(isVisible)
                    .slice(-1)[0] || document;
                for (const [placeholder, value] of dateMap) {
                    const inputs = [...dialog.querySelectorAll(`input[placeholder='${placeholder}']`)].filter((el) => isVisible(el) && !el.disabled);
                    for (const input of inputs) {
                        if ((input.value || '').trim()) continue;
                        setValue(input, value);
                        result.push(`${placeholder}=${value}`);
                    }
                }
                return result;
            }"""
        )
        return [str(item) for item in updates]

    def _fill_dialog_required_fields(self, defaults: dict[str, str]) -> list[str]:
        updates = self.page.evaluate(
            r"""(defaults) => {
                const result = [];
                const isVisible = (el) => {
                    if (!el) return false;
                    const st = window.getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 1 && r.height > 1;
                };
                const setValue = (input, value) => {
                    input.focus();
                    input.value = value;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.blur();
                };

                const partyType = (defaults.party_type || 'natural').trim();
                const defaultNaturalId = '110101' + '19900307' + '7719';
                const naturalId = /^\d{17}[\dXx]$/.test((defaults.id_number || '').trim())
                    ? (defaults.id_number || '').trim()
                    : defaultNaturalId;
                const naturalMap = [
                    [['姓名'], defaults.name || '张三'],
                    [['证件号码', '身份证号码'], naturalId],
                    [['出生日期', '出生年月日'], defaults.birth_date || '1990-01-01'],
                    [['年龄'], defaults.age || '36'],
                    [['手机号码'], defaults.phone || '13800000000'  // pragma: allowlist secret],
                    [['经常居住地', '住所地', '地址'], defaults.address || '广东省广州市天河区测试地址1号'],
                ];
                const legalMap = [
                    [['单位名称', '名称'], defaults.unit_name || defaults.name || '测试公司'],
                    [['证照号码', '统一社会信用代码'], defaults.license_number || defaults.id_number || '91440101MA59TEST8X'],
                    [['法定代表人'], defaults.legal_representative || '张三'],
                    [['主要负责人'], defaults.principal || defaults.legal_representative || '张三'],
                    [['手机号码'], defaults.phone || '13800000000'  // pragma: allowlist secret],
                    [['单位地址', '住所地', '地址'], defaults.unit_address || defaults.address || '广东省广州市天河区测试地址1号'],
                ];
                const commonMap = [
                    [['财产所有人'], defaults.owner_name || defaults.name || '张三'],
                    [['财产信息'], defaults.property_info || ''],
                    [['价值', '财产价值'], defaults.property_value || ''],
                ];

                const agentMap = [
                    [['代理人姓名', '姓名'], defaults.name || '张三'],
                    [['执业证件号码'], defaults.license_number || ''],
                    [['证件号码', '身份证号码'], defaults.id_number || defaultNaturalId],
                    [['手机号码'], defaults.phone || '13800000000'  // pragma: allowlist secret],
                    [['代理人所在律所'], defaults.law_firm || ''],
                ];

                const propertyMap = [
                    [['财产所有人'], defaults.owner_name || defaults.name || '张三'],
                    [['房产坐落位置', '具体位置'], defaults.property_location || defaults.property_info || ''],
                    [['房产证号'], defaults.property_cert_no || ''],
                    [['财产信息', '描述'], defaults.property_info || ''],
                    [['价值', '财产价值'], defaults.property_value || ''],
                ];

                const dynamicMap = [
                    ...(partyType === 'agent' ? agentMap : (partyType === 'property' ? propertyMap : (partyType === 'natural' ? naturalMap : legalMap))),
                    ...commonMap,
                ];

                const fallbackMap = [
                    [['姓名', '单位名称', '名称', '代理人姓名'], defaults.name || '张三'],
                    [['执业证件号码'], defaults.license_number || ''],
                    [['证件号码', '身份证号码'], /^\d{17}[\dXx]$/.test((defaults.id_number || '').trim()) ? (defaults.id_number || '').trim() : defaultNaturalId],
                    [['证照号码', '统一社会信用代码'], '91440101MA59TEST8X'],
                    [['法定代表人', '主要负责人'], defaults.legal_representative || '张三'],
                    [['手机号码'], defaults.phone || '13800000000'  // pragma: allowlist secret],
                    [['代理人所在律所'], defaults.law_firm || ''],
                    [['出生日期', '出生年月日'], defaults.birth_date || '1990-01-01'],
                    [['年龄'], defaults.age || '36'],
                    [['经常居住地', '住所地', '单位地址', '地址'], defaults.address || ''],
                    [['房产坐落位置', '具体位置'], defaults.property_location || ''],
                    [['房产证号'], defaults.property_cert_no || ''],
                    [['财产信息'], defaults.property_info || ''],
                    [['价值', '财产价值'], defaults.property_value || ''],
                    [['财产所有人'], defaults.owner_name || defaults.name || '张三'],
                ];
                const fieldMap = [...dynamicMap, ...fallbackMap];

                const dialog = [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper,.fd-com-layer,#addSQR')]
                    .filter(isVisible)
                    .slice(-1)[0] || document;
                const items = [...dialog.querySelectorAll('.el-form-item')].filter(isVisible);
                for (const item of items) {
                    const label = (item.querySelector('.el-form-item__label')?.innerText || '').replace(/\s+/g, ' ').trim();
                    const input = item.querySelector('input:not([type="hidden"]), textarea');
                    if (!input || input.disabled || input.readOnly) continue;
                    if ((input.value || '').trim()) continue;

                    for (const [keys, value] of fieldMap) {
                        if (!value) continue;
                        if (keys.some((key) => label.includes(key))) {
                            setValue(input, value);
                            result.push(`${label || keys[0]}=${value}`);
                            break;
                        }
                    }
                }

                const fillByPlaceholder = (placeholder, value) => {
                    if (!value) return;
                    const targets = [...dialog.querySelectorAll(`input[placeholder='${placeholder}']`)]
                        .filter((el) => isVisible(el) && !el.disabled && !el.readOnly && !(el.value || '').trim());
                    for (const input of targets) {
                        setValue(input, value);
                        result.push(`${placeholder}=${value}`);
                    }
                };
                fillByPlaceholder('区号', defaults.telephone_area_code || '');
                fillByPlaceholder('电话', defaults.telephone_number || '');
                fillByPlaceholder('分机号', defaults.telephone_extension || '');

                const longTerm = [...document.querySelectorAll('label, span, div')]
                    .find((el) => isVisible(el) && (el.innerText || '').includes('长期有效'));
                if (longTerm) {
                    longTerm.click();
                    result.push('长期有效=已选');
                }

                return result;
            }""",
            defaults,
        )
        return [str(item) for item in updates]

    def _fill_dialog_fields_with_playwright(self, defaults: dict[str, str], target: str) -> list[str]:
        updates: list[str] = []

        def _fill_first_visible(placeholder: str, value: str) -> None:
            if not value:
                return
            locator = self.page.locator(f"input[placeholder='{placeholder}']")
            for i in range(locator.count()):
                field = locator.nth(i)
                try:
                    if not field.is_visible() or field.is_disabled():
                        continue
                    field.click(timeout=1200)
                    field.fill(value, timeout=1200)
                    field.press("Enter", timeout=1200)
                    updates.append(f"{placeholder}={value}")
                    return
                except Exception:
                    continue

        def _select_first_visible_option(preferred_texts: list[str]) -> str | None:
            options = self.page.locator(".el-select-dropdown__item:not(.is-disabled)")
            visible: list[str] = []
            for i in range(options.count()):
                option = options.nth(i)
                try:
                    if not option.is_visible():
                        continue
                    text = (option.inner_text() or "").strip()
                    if not text:
                        continue
                    visible.append(text)
                except Exception:
                    continue

            if not visible:
                return None

            chosen = visible[0]
            for preferred in preferred_texts:
                cleaned = preferred.strip()
                if not cleaned:
                    continue
                matched = next((text for text in visible if cleaned in text or text in cleaned), None)
                if matched:
                    chosen = matched
                    break

            for i in range(options.count()):
                option = options.nth(i)
                try:
                    if not option.is_visible():
                        continue
                    text = (option.inner_text() or "").strip()
                    if text != chosen:
                        continue
                    option.click(timeout=1500)
                    return text
                except Exception:
                    continue
            return None

        def _select_dropdown_by_label(label_keyword: str, preferred_texts: list[str]) -> bool:
            selected_text = self._force_vue_select_by_label(label_keyword, preferred_texts)  # type: ignore[attr-defined]
            if selected_text:
                updates.append(f"{label_keyword}={selected_text}")
                return True
            return False

        _fill_first_visible("开始日期", "2020-01-01")
        _fill_first_visible("结束日期", "2099-12-31")
        _fill_first_visible("选择日期", defaults.get("birth_date") or "1990-01-01")
        _fill_first_visible("区号", defaults.get("telephone_area_code") or "")
        _fill_first_visible("电话", defaults.get("telephone_number") or "")
        _fill_first_visible("分机号", defaults.get("telephone_extension") or "")

        normalized_party_type = self._normalize_party_type(defaults.get("party_type") or "natural")  # type: ignore[attr-defined]
        if target in {"applicant", "respondent"} and normalized_party_type in {"legal", "non_legal_org"}:
            selected_unit_nature = self._force_vue_select_by_label(  # type: ignore[attr-defined]
                "单位性质", ["企业", defaults.get("unit_nature") or "", "其他"]
            )
            if selected_unit_nature:
                updates.append(f"单位性质={selected_unit_nature}")

        if target == "plaintiff_agent":
            selected = self.page.evaluate(
                r"""() => {
                    const isVisible = (el) => {
                        if (!el) return false;
                        const st = window.getComputedStyle(el);
                        if (st.display === 'none' || st.visibility === 'hidden') return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 1 && r.height > 1;
                    };
                    const dialog = [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper,.fd-com-layer,#addSQR')].filter(isVisible).slice(-1)[0] || document;
                    const row = [...dialog.querySelectorAll('.el-form-item')].find((it) => ((it.querySelector('.el-form-item__label')?.innerText || '').includes('所属原告')));
                    if (!row) return false;

                    const checkboxes = [...row.querySelectorAll('input[type="checkbox"]')].filter((el) => !el.disabled);
                    if (checkboxes.length > 0) {
                        const first = checkboxes[0];
                        if (!first.checked) {
                            const clickNode = first.closest('label') || first.parentElement || first;
                            clickNode.click();
                        }
                        first.dispatchEvent(new Event('change', { bubbles: true }));
                        return !!first.checked;
                    }

                    const labels = [...row.querySelectorAll('.el-checkbox, .el-checkbox__label, label, span, div')]
                        .filter((el) => isVisible(el) && (el.innerText || '').trim());
                    if (labels.length > 0) {
                        labels[0].click();
                        return true;
                    }
                    return false;
                }"""
            )
            if selected:
                updates.append("所属原告=已选")

        if target == "property_clue":
            selected_property_type = self._force_vue_select_by_label(  # type: ignore[attr-defined]
                "财产类型", ["其他", defaults.get("property_type") or "", "其他"]
            )
            if selected_property_type:
                updates.append(f"财产类型={selected_property_type}")

            _select_dropdown_by_label(
                "财产所有人",
                [defaults.get("owner_name") or "", defaults.get("name") or ""],
            )
            province_value = defaults.get("property_province") or "广东省"
            _select_dropdown_by_label("房产坐落位置", [province_value.replace("省", ""), province_value])

            property_updates = self.page.evaluate(
                r"""(args) => {
                    const ownerName = args.ownerName || '';
                    const provinceName = args.provinceName || '广东省';
                    const provinceKeyword = (provinceName || '广东省').replace('省', '');
                    const location = args.location || '';
                    const out = { province: false, location: false };
                    const isVisible = (el) => {
                        if (!el) return false;
                        const st = window.getComputedStyle(el);
                        if (st.display === 'none' || st.visibility === 'hidden') return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 1 && r.height > 1;
                    };
                    const setValue = (input, value) => {
                        input.focus();
                        input.value = value;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        input.blur();
                    };

                    const dialog = [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper,.fd-com-layer,#addSQR')].filter(isVisible).slice(-1)[0] || document;
                    const locationRow = [...dialog.querySelectorAll('.el-form-item')].find((it) => ((it.querySelector('.el-form-item__label')?.innerText || '').includes('房产坐落位置')));
                    if (locationRow) {
                        const sfInput = locationRow.querySelector('.fd-sf input.el-input__inner');
                        if (sfInput && !sfInput.disabled) {
                            sfInput.click();
                            const opts = [...document.querySelectorAll('.el-select-dropdown__item, .el-option, [role="option"], .el-popper li, .el-cascader-node__label')]
                                .filter((el) => isVisible(el));
                            let target = opts.find((el) => (el.innerText || '').includes(provinceKeyword || '广东'));
                            if (!target) target = opts.find((el) => (el.innerText || '').includes(provinceName || '广东'));
                            if (!target) target = opts.find((el) => (el.innerText || '').trim());
                            if (target) {
                                target.click();
                                out.province = true;
                            }
                        }

                        const editable = [...locationRow.querySelectorAll('input.el-input__inner')]
                            .find((el) => isVisible(el) && !el.disabled && !el.readOnly);
                        if (editable) {
                            setValue(editable, location || '');
                            out.location = true;
                        }
                    }

                    return out;
                }""",
                {
                    "ownerName": defaults.get("owner_name") or defaults.get("name") or "",
                    "provinceName": defaults.get("property_province") or "广东省",
                    "location": defaults.get("property_location") or "",
                },
            )
            if bool((property_updates or {}).get("province")):
                updates.append("省份=已选")
            if bool((property_updates or {}).get("location")):
                updates.append(f"具体位置={defaults.get('property_location') or ''}")

            _fill_first_visible("请选择省份", defaults.get("property_province") or "广东省")
            self.page.evaluate(
                r"""(province) => {
                    const isVisible = (el) => {
                        if (!el) return false;
                        const st = window.getComputedStyle(el);
                        if (st.display === 'none' || st.visibility === 'hidden') return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 1 && r.height > 1;
                    };
                    const setValue = (input, value) => {
                        input.focus();
                        input.value = value;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        input.blur();
                    };
                    const dialog = [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper,.fd-com-layer,#addSQR')].filter(isVisible).slice(-1)[0] || document;
                    const provinceInputs = [...dialog.querySelectorAll('input')]
                        .filter((el) => isVisible(el) && !el.disabled && ((el.placeholder || '').includes('省') || (el.parentElement?.innerText || '').includes('省份')));
                    for (const input of provinceInputs) {
                        if (!(input.value || '').trim()) setValue(input, province || '广东省');
                    }
                }""",
                defaults.get("property_province") or "广东省",
            )

            cascaders = self.page.locator(".el-dialog .el-cascader, #addSQR .el-cascader")
            if cascaders.count() > 0:
                try:
                    cascaders.first.click(force=True, timeout=2000)
                    self._random_wait(0.2, 0.4)  # type: ignore[attr-defined]
                    gd_nodes = self.page.locator(".el-cascader-node__label").filter(has_text="广东")
                    clicked = False
                    if gd_nodes.count() > 0:
                        for i in range(gd_nodes.count()):
                            node = gd_nodes.nth(i)
                            if not node.is_visible():
                                continue
                            node.click(timeout=1500)
                            clicked = True
                            break
                    if not clicked:
                        all_nodes = self.page.locator(".el-cascader-node__label")
                        for i in range(all_nodes.count()):
                            node = all_nodes.nth(i)
                            if not node.is_visible():
                                continue
                            node.click(timeout=1200)
                            clicked = True
                            break
                    if clicked:
                        updates.append("省份=广东")
                except Exception:
                    pass

            updates.extend(self._fill_property_clue_dialog_v15(defaults))

        return updates

    def _fill_property_clue_dialog_v15(self, defaults: dict[str, str]) -> list[str]:
        updates: list[str] = []
        owner_name = str(defaults.get("owner_name") or defaults.get("name") or "张三").strip() or "张三"
        province_name = str(defaults.get("property_province") or "广东省").strip() or "广东省"
        province_keyword = province_name.replace("省", "")

        try:
            type_inputs = self.page.locator(
                ".el-dialog input[placeholder='请选择财产类型'], #addSQR input[placeholder='请选择财产类型']"
            )
            for i in range(type_inputs.count()):
                field = type_inputs.nth(i)
                if not field.is_visible() or field.is_disabled():
                    continue
                selected = False
                for retry in range(4):
                    reopened = self._reopen_and_search_dropdown_input(  # type: ignore[attr-defined]
                        field,
                        "其他",
                        force_reset=retry > 0,
                        open_timeout_ms=2500,
                        submit_enter=True,
                    )
                    if not reopened:
                        self._random_wait(0.3, 0.6)  # type: ignore[attr-defined]
                        continue
                    self._wait_select_options_ready(candidates=["其他"], timeout_ms=min(self.MAX_SLOW_WAIT_MS, 45000))  # type: ignore[attr-defined]
                    selected = self._choose_dropdown_item("其他")  # type: ignore[attr-defined]
                    if selected:
                        break
                    self._close_popovers()  # type: ignore[attr-defined]
                    self._random_wait(0.5, 0.8)  # type: ignore[attr-defined]
                if selected:
                    updates.append("财产类型=其他")
                    break
        except Exception:
            pass

        try:
            owner_inputs = self.page.locator(
                ".el-dialog input[placeholder='请选择财产所有人'], #addSQR input[placeholder='请选择财产所有人']"
            )
            for i in range(owner_inputs.count()):
                field = owner_inputs.nth(i)
                if not field.is_visible() or field.is_disabled():
                    continue
                selected = False
                for retry in range(4):
                    reopened = self._reopen_and_search_dropdown_input(  # type: ignore[attr-defined]
                        field,
                        owner_name,
                        force_reset=retry > 0,
                        open_timeout_ms=2500,
                        submit_enter=True,
                    )
                    if not reopened:
                        self._random_wait(0.4, 0.8)  # type: ignore[attr-defined]
                        continue
                    self._wait_select_options_ready(  # type: ignore[attr-defined]
                        candidates=[owner_name], timeout_ms=min(self.MAX_SLOW_WAIT_MS, 60000)
                    )
                    selected = self._choose_dropdown_item(owner_name)  # type: ignore[attr-defined]
                    if not selected:
                        selected = self._choose_dropdown_item("")  # type: ignore[attr-defined]
                    if selected:
                        break
                    self._close_popovers()  # type: ignore[attr-defined]
                    self._random_wait(0.6, 1.0)  # type: ignore[attr-defined]
                if selected:
                    updates.append("财产所有人=已选")
                    break
        except Exception:
            pass

        try:
            province_inputs = self.page.locator(
                ".el-dialog .fd-sf input.el-input__inner, #addSQR .fd-sf input.el-input__inner"
            )
            if province_inputs.count() > 0:
                field = province_inputs.first
                if field.is_visible() and not field.is_disabled():
                    selected = False
                    for retry in range(4):
                        reopened = self._reopen_and_search_dropdown_input(  # type: ignore[attr-defined]
                            field,
                            province_keyword if retry < 3 else province_name,
                            force_reset=retry > 0,
                            open_timeout_ms=2500,
                            submit_enter=True,
                        )
                        if not reopened:
                            self._random_wait(0.4, 0.8)  # type: ignore[attr-defined]
                            continue
                        self._wait_select_options_ready(  # type: ignore[attr-defined]
                            candidates=[province_keyword, province_name],
                            timeout_ms=min(self.MAX_SLOW_WAIT_MS, 60000),
                        )
                        selected = self._choose_dropdown_item(province_keyword)  # type: ignore[attr-defined]
                        if not selected:
                            selected = self._choose_dropdown_item(province_name)  # type: ignore[attr-defined]
                        if not selected:
                            selected = self._choose_dropdown_item("")  # type: ignore[attr-defined]
                        if selected:
                            break
                        self._close_popovers()  # type: ignore[attr-defined]
                        self._random_wait(0.5, 0.9)  # type: ignore[attr-defined]
                    if selected:
                        updates.append(f"省份={province_name}")
        except Exception:
            pass

        filled_fields = self.page.evaluate(
            r"""(args) => {
                const values = args || {};
                const isVisible = (el) => {
                    if (!el) return false;
                    const st = window.getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 1 && r.height > 1;
                };
                const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
                const setValue = (input, value) => {
                    input.focus();
                    input.value = value;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.blur();
                };

                const fillRules = [
                    { labels: ['财产信息', '描述'], value: values.propertyInfo || '' },
                    { labels: ['房产证号'], value: values.propertyCertNo || '' },
                    { labels: ['价值', '财产价值'], value: values.propertyValue || '' },
                    { labels: ['具体位置', '房产坐落位置'], value: values.propertyLocation || '' },
                ];

                const dialog = [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper,.fd-com-layer,#addSQR')].filter(isVisible).slice(-1)[0] || document;
                const items = [...dialog.querySelectorAll('.el-form-item')].filter(isVisible);
                const result = [];

                for (const item of items) {
                    const label = norm(item.querySelector('.el-form-item__label')?.innerText || '');
                    if (!label) continue;
                    const input = item.querySelector('input:not([type="hidden"]):not([readonly]), textarea');
                    if (!input || input.disabled) continue;
                    if ((input.value || '').trim()) continue;

                    for (const rule of fillRules) {
                        if (!rule.value) continue;
                        if (rule.labels.some((kw) => label.includes(kw))) {
                            setValue(input, rule.value);
                            result.push(`${label}=${rule.value}`);
                            break;
                        }
                    }
                }
                return result;
            }""",
            {
                "propertyInfo": defaults.get("property_info") or "",
                "propertyCertNo": defaults.get("property_cert_no") or "",
                "propertyValue": defaults.get("property_value") or "",
                "propertyLocation": defaults.get("property_location") or "",
            },
        )
        updates.extend([str(item) for item in (filled_fields or [])])
        self._close_popovers()  # type: ignore[attr-defined]
        return updates

    def _retry_property_clue_save_on_province_error(self, defaults: dict[str, str]) -> bool:
        for _ in range(4):
            try:
                self._fill_property_clue_dialog_v15(defaults)

                self._random_wait(0.2, 0.4)  # type: ignore[attr-defined]
                self._click_first_enabled_button(["保存", "确定"])  # type: ignore[attr-defined]
                self._random_wait(0.6, 0.9)  # type: ignore[attr-defined]

                errors = self._get_visible_form_errors()  # type: ignore[attr-defined]
                has_required_select_error = any(("请选择省份" in err) or ("请选择财产所有人" in err) for err in errors)
                if not has_required_select_error:
                    return True
            except Exception:
                continue
        return False
