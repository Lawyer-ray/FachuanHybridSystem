"""gTwo 财产线索专用对话框逻辑。"""

from __future__ import annotations

from typing import Any


class GuaranteeDialogPropertyClueMixin:
    """gTwo 财产线索对话框填写与重试。"""

    page: Any
    MAX_SLOW_WAIT_MS: int

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
