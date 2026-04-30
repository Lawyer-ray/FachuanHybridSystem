"""gOne 页面表单填写：法院、案由、金额、保全公司等。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("apps.automation")


class GuaranteeFormFillingMixin:
    """gOne 页面表单填写：法院、案由、金额、保全公司等。"""

    page: Any
    MAX_SLOW_WAIT_MS: int

    def _choose_court(self, court_name: str) -> bool:
        target_name = str(court_name or "").strip()
        if not target_name:
            return False

        keyword = self._extract_court_keyword(target_name)
        short_name = target_name.replace("人民法院", "").strip()
        court_input = self.page.locator("input[placeholder*='法院']").first
        if court_input.count() == 0:
            return False

        search_terms = [term for term in [keyword, short_name, target_name] if term]
        candidates = [target_name]
        if short_name and short_name not in candidates:
            candidates.append(short_name)
        if keyword and keyword not in candidates:
            candidates.append(keyword)

        for attempt in range(6):
            term = search_terms[attempt % len(search_terms)] if search_terms else target_name

            for refresh_round in range(2):
                reopened = self._reopen_and_search_court_dropdown(
                    court_input,
                    term,
                    force_reset=refresh_round > 0,
                )
                if not reopened:
                    self._random_wait(1.0, 1.6)  # type: ignore[attr-defined]
                    continue

                ready = self._wait_court_options_ready(candidates=candidates, timeout_ms=self.MAX_SLOW_WAIT_MS)  # type: ignore[attr-defined]
                if not ready:
                    self._close_popovers()  # type: ignore[attr-defined]
                    self._random_wait(1.2, 2.0)  # type: ignore[attr-defined]
                    continue

                selected_text = str(
                    self.page.evaluate(
                        r"""(names) => {
                            const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
                            const isVisible = (el) => {
                                if (!el) return false;
                                const st = window.getComputedStyle(el);
                                if (st.display === 'none' || st.visibility === 'hidden') return false;
                                const r = el.getBoundingClientRect();
                                return r.width > 1 && r.height > 1;
                            };

                            const targets = (names || []).map((n) => norm(n)).filter(Boolean);
                            const nodes = [...document.querySelectorAll('.el-tree-node__content')]
                                .filter((node) => isVisible(node))
                                .map((node) => ({ node, text: norm(node.innerText || '') }))
                                .filter((item) => item.text && !item.text.includes('暂无数据'));

                            if (nodes.length === 0) return '';

                            for (const target of targets) {
                                const exact = nodes.find((item) => item.text === target);
                                if (exact) {
                                    exact.node.click();
                                    return exact.text;
                                }
                            }

                            for (const target of targets) {
                                const suffix = nodes.find((item) => item.text.endsWith(target));
                                if (suffix) {
                                    suffix.node.click();
                                    return suffix.text;
                                }
                            }

                            for (const target of targets) {
                                const partial = nodes.find((item) => item.text.includes(target));
                                if (partial) {
                                    partial.node.click();
                                    return partial.text;
                                }
                            }

                            return '';
                        }""",
                        candidates,
                    )
                    or ""
                ).strip()

                if not selected_text:
                    self._close_popovers()  # type: ignore[attr-defined]
                    self._random_wait(1.2, 2.0)  # type: ignore[attr-defined]
                    continue

                self._random_wait(0.8, 1.3)  # type: ignore[attr-defined]
                input_value = ""
                try:
                    input_value = (court_input.input_value() or "").strip()
                except Exception:
                    input_value = ""

                if (
                    selected_text in input_value
                    or target_name in input_value
                    or (short_name and short_name in input_value)
                ):
                    self._close_popovers()  # type: ignore[attr-defined]
                    return True

                self._close_popovers()  # type: ignore[attr-defined]
                self._random_wait(1.0, 1.8)  # type: ignore[attr-defined]

        logger.warning("court_guarantee_court_not_stable", extra={"target_name": target_name})
        return False

    def _click_radio_in_form_item(self, label_keywords: list[str], option_text: str) -> bool:
        cleaned_option = str(option_text or "").strip()
        cleaned_keywords = [str(keyword).strip() for keyword in label_keywords if str(keyword).strip()]
        if not cleaned_option or not cleaned_keywords:
            return False

        ready = self._wait_form_item_option_ready(  # type: ignore[attr-defined]
            label_keywords=cleaned_keywords,
            option_text=cleaned_option,
            timeout_ms=self.MAX_SLOW_WAIT_MS,
        )
        if not ready:
            logger.warning(
                "court_guarantee_radio_option_not_ready",
                extra={"label_keywords": cleaned_keywords, "option_text": cleaned_option},
            )
            return False

        for _ in range(8):
            selected = bool(
                self.page.evaluate(
                    r"""(args) => {
                        const keywords = args.keywords || [];
                        const option = (args.option || '').trim();
                        const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
                        const isVisible = (el) => {
                            if (!el) return false;
                            const st = window.getComputedStyle(el);
                            if (st.display === 'none' || st.visibility === 'hidden') return false;
                            const r = el.getBoundingClientRect();
                            return r.width > 1 && r.height > 1;
                        };

                        const formItems = [...document.querySelectorAll('.el-form-item')].filter(isVisible);
                        for (const item of formItems) {
                            const label = norm(item.querySelector('.el-form-item__label')?.innerText || '');
                            if (!label || !keywords.some((kw) => label.includes(kw))) continue;

                            const candidates = [...item.querySelectorAll('label, .el-radio, .el-radio-wrapper, .el-radio-button, .el-radio-button__inner, span, div')]
                                .filter((el) => isVisible(el))
                                .map((el) => ({ el, text: norm(el.innerText || '') }))
                                .filter((item) => item.text);

                            const matched = candidates.find((entry) => entry.text === option)
                                || candidates.find((entry) => entry.text.includes(option));
                            if (!matched) continue;

                            const clickNode = matched.el.closest('label') || matched.el;
                            clickNode.click();

                            const checkedInItem = !!item.querySelector('.is-checked input[type="radio"], input[type="radio"]:checked, .is-checked .el-radio__label, .is-checked .el-radio-button__inner');
                            if (checkedInItem) return true;
                        }
                        return false;
                    }""",
                    {"keywords": cleaned_keywords, "option": cleaned_option},
                )
            )
            if selected:
                self._random_wait(0.6, 1.1)  # type: ignore[attr-defined]
                return True
            self._random_wait(1.0, 1.6)  # type: ignore[attr-defined]

        return False

    def _click_radio_by_text(self, text: str) -> bool:
        option = self.page.locator("label, .el-radio-wrapper").filter(has_text=text).first
        if option.count() == 0:
            return False
        try:
            option.click(timeout=3000)
        except Exception:
            option.click(force=True)
        self._random_wait(0.3, 0.6)  # type: ignore[attr-defined]
        return True

    def _fill_case_number(self, case_data: dict[str, Any]) -> dict[str, bool]:
        result = {"case_type": False, "year": False, "court_code": False, "type_code": False, "seq": False}

        case_type_input = self.page.locator("input[placeholder*='案件类型']").first
        if case_type_input.count() > 0:
            case_type_input.click()
            self._random_wait(0.4, 0.7)  # type: ignore[attr-defined]
            result["case_type"] = self._choose_dropdown_item("民事")
            self._close_popovers()  # type: ignore[attr-defined]

        year_input = self.page.locator("input[placeholder='年份']").first
        year = str(case_data.get("case_year") or "")
        if year_input.count() > 0 and year:
            year_input.click()
            self._random_wait(0.4, 0.7)  # type: ignore[attr-defined]
            result["year"] = self._choose_dropdown_item(year)
            self._close_popovers()  # type: ignore[attr-defined]

        for placeholder, key in (
            ("法院代字", "case_court_code"),
            ("类型代字", "case_type_code"),
            ("案件序号", "case_seq"),
        ):
            field = self.page.locator(f"input[placeholder='{placeholder}']").first
            value = str(case_data.get(key) or "")
            if field.count() > 0 and value:
                field.fill(value)
                result[
                    "court_code" if key == "case_court_code" else "type_code" if key == "case_type_code" else "seq"
                ] = True

        return result

    def _fill_case_cause(self, cause_name: str, cause_candidates: list[str] | None = None) -> bool:
        cause_input = self.page.locator("input[placeholder*='案由']").first
        if cause_input.count() == 0:
            return False

        candidates = [str(c).strip() for c in (cause_candidates or []) if str(c).strip()]
        if cause_name.strip() and cause_name.strip() not in candidates:
            candidates.insert(0, cause_name.strip())
        if "买卖合同纠纷" not in candidates:
            candidates.append("买卖合同纠纷")

        search_terms = candidates[:3] if candidates else ["买卖合同纠纷"]
        for attempt in range(6):
            term = search_terms[attempt % len(search_terms)]
            reopened = self._reopen_and_search_dropdown_input(
                cause_input,
                term,
                force_reset=attempt > 0,
            )
            if not reopened:
                self._random_wait(0.6, 1.0)
                continue

            if not self._wait_tree_options_ready(candidates=candidates, timeout_ms=self.MAX_SLOW_WAIT_MS):
                self._close_popovers()
                self._random_wait(1.0, 1.6)
                continue

            clicked = self.page.evaluate(
                r"""(incomingCandidates) => {
                    const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
                    const isVisible = (el) => {
                        if (!el) return false;
                        const st = window.getComputedStyle(el);
                        if (st.display === 'none' || st.visibility === 'hidden') return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 1 && r.height > 1;
                    };
                    const candidates = (incomingCandidates || []).map((s) => norm(s)).filter(Boolean);
                    const nodes = [...document.querySelectorAll('.el-tree-node__content')]
                        .filter((node) => isVisible(node));

                    for (const target of candidates) {
                        const exact = nodes.find((node) => norm(node.innerText) === target);
                        if (exact) {
                            exact.click();
                            return true;
                        }
                    }

                    for (const target of candidates) {
                        const partial = nodes.find((node) => {
                            const text = norm(node.innerText);
                            return text && text.includes(target);
                        });
                        if (partial) {
                            partial.click();
                            return true;
                        }
                    }

                    return false;
                }""",
                candidates,
            )
            self._close_popovers()
            if bool(clicked):
                return True
            self._random_wait(0.8, 1.3)

        logger.warning(
            "court_guarantee_cause_not_stable", extra={"cause_name": cause_name, "candidates": candidates[:5]}
        )
        return False

    def _choose_insurance(self, preferred_name: str) -> str | None:
        select = self.page.locator(".el-select").last
        if select.count() == 0:
            return None

        keyword_candidates = ["平安", "保险", "担保", "公司"]
        search_terms = [term for term in [preferred_name, *keyword_candidates] if str(term).strip()]

        for attempt in range(8):
            try:
                self._close_popovers()
                self._random_wait(0.4, 0.7)
                select.click(force=True, timeout=2500)
            except Exception:
                self._random_wait(0.4, 0.7)
                continue

            search_input = self.page.locator(".el-select-dropdown input.el-input__inner").first
            if search_input.count() > 0 and search_terms:
                term = str(search_terms[attempt % len(search_terms)]).strip()
                if term:
                    self._reopen_and_search_dropdown_input(
                        search_input,
                        term,
                        force_reset=attempt > 0,
                        open_timeout_ms=2200,
                        submit_enter=True,
                    )

            self._wait_select_options_ready(
                candidates=[preferred_name, *keyword_candidates],
                timeout_ms=min(self.MAX_SLOW_WAIT_MS, 60000),
            )
            self._random_wait(0.4, 0.8)

            chosen_text = str(
                self.page.evaluate(
                    r"""(args) => {
                        const preferred = (args.preferred || '').trim();
                        const keywords = Array.isArray(args.keywords) ? args.keywords : [];
                        const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
                        const isVisible = (el) => {
                            if (!el) return false;
                            const st = window.getComputedStyle(el);
                            if (st.display === 'none' || st.visibility === 'hidden') return false;
                            const r = el.getBoundingClientRect();
                            return r.width > 1 && r.height > 1;
                        };

                        const options = [...document.querySelectorAll('.el-select-dropdown__item')]
                            .filter((el) => isVisible(el) && !el.classList.contains('is-disabled'));
                        if (options.length === 0) return '';

                        const withText = options
                            .map((el) => ({ el, text: norm(el.innerText || '') }))
                            .filter((item) => item.text && !item.text.includes('暂无数据'));
                        if (withText.length === 0) return '';

                        let target = null;
                        if (preferred) {
                            target = withText.find((item) => item.text.includes(preferred));
                        }
                        if (!target && keywords.length > 0) {
                            target = withText.find((item) => keywords.some((kw) => item.text.includes(kw)));
                        }
                        if (!target) {
                            target = withText[0];
                        }

                        if (!target || !target.el) return '';
                        target.el.click();
                        return target.text;
                    }""",
                    {"preferred": preferred_name, "keywords": keyword_candidates},
                )
                or ""
            ).strip()

            if chosen_text:
                self._close_popovers()
                return chosen_text

            self._close_popovers()
            self._random_wait(1.5, 2.5)

        logger.warning("court_guarantee_insurance_options_not_ready", extra={"preferred_name": preferred_name})
        self._close_popovers()
        return None

    def _fill_consultant_code(self, consultant_code: str) -> bool:
        code = consultant_code.strip()
        if not code:
            return False

        selectors = [
            "input[placeholder*='咨询员编号']",
            "input[placeholder*='咨询编号']",
            "input[placeholder*='咨询员']",
        ]
        for selector in selectors:
            field = self.page.locator(selector).first
            if field.count() == 0:
                continue
            try:
                if field.is_disabled():
                    continue
                field.click()
                field.fill(code)
                self._random_wait(0.2, 0.4)
                return True
            except Exception:
                continue

        filled = self.page.evaluate(
            r"""(value) => {
                const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
                const labels = [...document.querySelectorAll('label, span, div')];
                for (const label of labels) {
                    const text = norm(label.innerText || '');
                    if (!text) continue;
                    if (!text.includes('咨询员编号') && !text.includes('咨询编号') && !text.includes('咨询员')) continue;
                    let container = label.closest('.el-form-item') || label.parentElement;
                    for (let depth = 0; depth < 4 && container; depth += 1) {
                        const input = container.querySelector('input');
                        if (input && !input.disabled) {
                            input.focus();
                            input.value = value;
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }
                        container = container.parentElement;
                    }
                }
                return false;
            }""",
            code,
        )
        if filled:
            self._random_wait(0.2, 0.4)
        return bool(filled)

    def _fill_amount(self, amount: Any) -> bool:
        raw = str(amount or "").strip().replace(",", "")
        if not raw:
            return False
        try:
            if float(raw) <= 0:
                return False
        except Exception:
            return False

        amount_input = self.page.locator("input[placeholder*='保全金额']").first
        if amount_input.count() == 0 or amount_input.is_disabled():
            return False
        amount_input.click()
        amount_input.fill(raw)
        self._random_wait(0.2, 0.4)
        return True

    def _choose_dropdown_item(self, preferred_text: str) -> bool:
        preferred = str(preferred_text or "").strip()
        for _ in range(3):
            items = self.page.locator(".el-select-dropdown__item")
            for i in range(items.count()):
                text = (items.nth(i).inner_text() or "").strip()
                if preferred and preferred in text:
                    items.nth(i).click(force=True)
                    self._random_wait(0.2, 0.4)
                    return True
            for i in range(items.count()):
                text = (items.nth(i).inner_text() or "").strip()
                if text:
                    items.nth(i).click(force=True)
                    self._random_wait(0.2, 0.4)
                    return True
            self._random_wait(0.4, 0.8)
        return False

    def _reopen_and_search_dropdown_input(
        self,
        dropdown_input: Any,
        search_text: str,
        *,
        force_reset: bool = False,
        open_timeout_ms: int = 5000,
        submit_enter: bool = True,
    ) -> bool:
        term = str(search_text or "").strip()
        if not term:
            return False

        try:
            self._close_popovers()
            self._random_wait(0.4, 0.8)

            dropdown_input.click(timeout=open_timeout_ms)
            self._random_wait(0.6, 1.1)

            if force_reset:
                try:
                    dropdown_input.press("Meta+a", timeout=1200)
                    dropdown_input.press("Backspace", timeout=1200)
                except Exception:
                    try:
                        dropdown_input.press("Control+a", timeout=1200)
                        dropdown_input.press("Backspace", timeout=1200)
                    except Exception:
                        pass

            dropdown_input.fill("")
            self._random_wait(0.4, 0.8)
            dropdown_input.fill(term)

            if submit_enter:
                try:
                    dropdown_input.press("Enter", timeout=2000)
                except Exception:
                    pass
            return True
        except Exception:
            return False

    def _reopen_and_search_court_dropdown(
        self, court_input: Any, search_text: str, *, force_reset: bool = False
    ) -> bool:
        return self._reopen_and_search_dropdown_input(
            court_input,
            search_text,
            force_reset=force_reset,
            open_timeout_ms=5000,
            submit_enter=True,
        )

    def _force_vue_select_by_label(self, label_keyword: str, preferred_texts: list[str]) -> str | None:
        selected = self.page.evaluate(
            r"""(args) => {
                const labelKeyword = args.labelKeyword || '';
                const preferredTexts = (args.preferredTexts || []).map((item) => (item || '').replace(/\s+/g, ' ').trim()).filter(Boolean);
                const isVisible = (el) => {
                    if (!el) return false;
                    const st = window.getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 1 && r.height > 1;
                };
                const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
                const dialog = [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper,.fd-com-layer,#addSQR')]
                    .filter(isVisible)
                    .slice(-1)[0] || document;
                const row = [...dialog.querySelectorAll('.el-form-item')]
                    .filter((item) => isVisible(item))
                    .find((item) => norm(item.querySelector('.el-form-item__label')?.innerText || '').includes(labelKeyword));
                if (!row) return '';

                const selectNodes = [...row.querySelectorAll('.el-select')];
                for (const selectEl of selectNodes) {
                    const vm = selectEl && selectEl.__vue__ ? selectEl.__vue__ : null;
                    if (!vm || !Array.isArray(vm.options) || vm.options.length === 0) continue;
                    let optionVm = null;
                    for (const preferred of preferredTexts) {
                        optionVm = vm.options.find((opt) => {
                            const text = norm(opt.currentLabel || opt.label || '');
                            return text === preferred || text.includes(preferred) || preferred.includes(text);
                        });
                        if (optionVm) break;
                    }
                    if (!optionVm) {
                        optionVm = vm.options.find((opt) => norm(opt.currentLabel || opt.label || '')) || null;
                    }
                    if (!optionVm) continue;
                    if (typeof vm.handleOptionSelect === 'function') {
                        vm.handleOptionSelect(optionVm, true);
                    }
                    if (typeof vm.$emit === 'function') {
                        vm.$emit('input', optionVm.value);
                        vm.$emit('change', optionVm.value);
                    }
                    return norm(optionVm.currentLabel || optionVm.label || '');
                }

                const trigger = row.querySelector('.el-select input.el-input__inner, .fd-sf input.el-input__inner, input.el-input__inner');
                if (!trigger || trigger.disabled || !isVisible(trigger)) return '';
                trigger.click();
                const options = [...document.querySelectorAll('.el-select-dropdown__item, .el-option, [role="option"], .el-popper li')]
                    .filter((el) => isVisible(el) && !el.classList.contains('is-disabled'));
                let target = null;
                for (const preferred of preferredTexts) {
                    target = options.find((el) => {
                        const text = norm(el.innerText || '');
                        return text === preferred || text.includes(preferred) || preferred.includes(text);
                    });
                    if (target) break;
                }
                if (!target) {
                    target = options.find((el) => norm(el.innerText || '')) || null;
                }
                if (!target) return '';
                const text = norm(target.innerText || '');
                target.click();
                trigger.dispatchEvent(new Event('change', { bubbles: true }));
                trigger.dispatchEvent(new Event('blur', { bubbles: true }));
                return text;
            }""",
            {"labelKeyword": label_keyword, "preferredTexts": preferred_texts},
        )
        self._close_popovers()
        selected_text = str(selected or "").strip()
        return selected_text or None

    @staticmethod
    def _extract_court_keyword(court_name: str) -> str:
        name = str(court_name or "").replace("人民法院", "").strip()
        for sep in ("区", "县"):
            if sep in name:
                idx = name.index(sep)
                return name[max(0, idx - 2) : idx + 1]
        if len(name) >= 4:
            return name[-4:]
        return name or "广东"
