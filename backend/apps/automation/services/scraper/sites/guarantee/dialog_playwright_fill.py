"""gTwo Playwright 增强填充逻辑。"""

from __future__ import annotations

from typing import Any


class GuaranteeDialogPlaywrightFillMixin:
    """gTwo 对话框中基于 Playwright 的增强填充方法。"""

    page: Any
    MAX_SLOW_WAIT_MS: int

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

            updates.extend(self._fill_property_clue_dialog_v15(defaults))  # type: ignore[attr-defined]

        return updates
