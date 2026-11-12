"""gTwo 表单字段填充 (select/date/required)。"""

from __future__ import annotations

from typing import Any

from .base_mixin import _random_wait


class GuaranteeDialogFieldFillingMixin:  # pragma: no cover
    """gTwo 对话框中的 select / date / required 字段填充。"""

    page: Any

    def _fill_dialog_select_fields(
        self, defaults: dict[str, str], target: str | None = None
    ) -> list[str]:  # pragma: no cover
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

                    const gender = norm(defaults.gender);
                    if (label.includes('性别') && gender) {
                        const genderOption = [...item.querySelectorAll('label, span, div')]
                            .find((el) => isVisible(el) && norm(el.innerText) === gender);
                        if (genderOption) {
                            genderOption.click();
                            result.push(`${label}=${gender}`);
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
                        prefer = forceEnterpriseUnitNature ? '企业' : (defaults.unit_nature || '');
                    }
                    if (label.includes('财产类型')) {
                        prefer = defaults.property_type || '';
                    }
                    if (label.includes('房产坐落位置')) {
                        prefer = (defaults.property_province || '').replace('省', '');
                    }

                    const selected = pickOption(prefer);
                    if (selected) result.push(`${label || 'select'}=${selected}`);
                }

                return result;
            }""",
            {"defaults": defaults, "target": target or ""},
        )
        _random_wait(0.2, 0.4)
        self._close_popovers()  # type: ignore[attr-defined]
        return [str(item) for item in updates]

    def _fill_dialog_date_fields(self) -> list[str]:  # pragma: no cover
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
                // 出生日期只填真实值；为空就不填，不回落到伪造生日。
                const dateMap = [
                    ['开始日期', '2020-01-01'],
                    ['结束日期', '2099-12-31'],
                    ['选择日期', (defaults.birth_date || '').trim()],
                ];
                const dialog = [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper,.fd-com-layer,#addSQR')]
                    .filter(isVisible)
                    .slice(-1)[0] || document;
                for (const [placeholder, value] of dateMap) {
                    if (!value) continue;
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

    def _fill_dialog_required_fields(self, defaults: dict[str, str]) -> list[str]:  # pragma: no cover
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
                // 证件号留空即不填该字段（下方 `if (!value) continue`），
                // 让法院表单自身的必填校验暴露问题，绝不填伪造号。
                const trimValue = (value) => (value || '').trim();
                const naturalId = /^\d{17}[\dXx]$/.test(trimValue(defaults.id_number))
                    ? trimValue(defaults.id_number)
                    : '';
                const naturalMap = [
                    [['姓名'], defaults.name || ''],
                    [['证件号码', '身份证号码'], naturalId],
                    [['出生日期', '出生年月日'], defaults.birth_date || ''],
                    [['年龄'], defaults.age || ''],
                    [['手机号码'], defaults.phone || ''],
                    [['经常居住地', '住所地', '地址'], defaults.address || ''],
                ];
                const legalMap = [
                    [['单位名称', '名称'], defaults.unit_name || defaults.name || ''],
                    [['证照号码', '统一社会信用代码'], defaults.license_number || defaults.id_number || ''],
                    [['法定代表人'], defaults.legal_representative || ''],
                    [['主要负责人'], defaults.principal || defaults.legal_representative || ''],
                    [['手机号码'], defaults.phone || ''],
                    [['单位地址', '住所地', '地址'], defaults.unit_address || defaults.address || ''],
                ];
                const commonMap = [
                    [['财产所有人'], defaults.owner_name || defaults.name || ''],
                    [['财产信息'], defaults.property_info || ''],
                    [['价值', '财产价值'], defaults.property_value || ''],
                ];

                const agentMap = [
                    [['代理人姓名', '姓名'], defaults.name || ''],
                    [['执业证件号码'], defaults.license_number || ''],
                    [['证件号码', '身份证号码'], trimValue(defaults.id_number)],
                    [['手机号码'], defaults.phone || ''],
                    [['代理人所在律所'], defaults.law_firm || ''],
                ];

                const propertyMap = [
                    [['财产所有人'], defaults.owner_name || defaults.name || ''],
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
                    [['姓名', '单位名称', '名称', '代理人姓名'], defaults.name || ''],
                    [['执业证件号码'], defaults.license_number || ''],
                    [['证件号码', '身份证号码'], naturalId],
                    [['证照号码', '统一社会信用代码'], defaults.license_number || defaults.id_number || ''],
                    [['法定代表人', '主要负责人'], defaults.legal_representative || ''],
                    [['手机号码'], defaults.phone || ''],
                    [['代理人所在律所'], defaults.law_firm || ''],
                    [['出生日期', '出生年月日'], defaults.birth_date || ''],
                    [['年龄'], defaults.age || ''],
                    [['经常居住地', '住所地', '单位地址', '地址'], defaults.address || ''],
                    [['房产坐落位置', '具体位置'], defaults.property_location || ''],
                    [['房产证号'], defaults.property_cert_no || ''],
                    [['财产信息'], defaults.property_info || ''],
                    [['价值', '财产价值'], defaults.property_value || ''],
                    [['财产所有人'], defaults.owner_name || defaults.name || ''],
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
