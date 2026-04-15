"""一张网申请担保 Playwright 服务。"""

from __future__ import annotations

import logging
import random
import re
import time
from typing import Any

from playwright.sync_api import Page

logger = logging.getLogger("apps.automation")


class CourtZxfwGuaranteeService:
    """一张网申请担保流程（到 gFive 预览页，不提交）。"""

    GUARANTEE_URL = "https://zxfw.court.gov.cn/yzwbqww/index.html#/CreateGuarantee/applyGuaranteeInformation/gOne"
    MAX_SLOW_WAIT_MS = 180000
    DEFAULT_POLL_MS = 1200
    DEFAULT_NATURAL_ID_NUMBER = "110101" + "19900307" + "7719"
    DEFAULT_LEGAL_ID_NUMBER = "91440101MA59TEST8X"

    def __init__(self, page: Page, *, save_debug: bool = False) -> None:
        self.page = page
        self.save_debug = save_debug

    def apply_guarantee(self, case_data: dict[str, Any]) -> dict[str, Any]:
        self.page.goto(self.GUARANTEE_URL, timeout=60000, wait_until="domcontentloaded")
        self._random_wait(4, 6)
        self._material_paths = [str(path) for path in (case_data.get("material_paths") or []) if str(path)]

        insurance_company_name = str(case_data.get("insurance_company_name") or "").strip()
        consultant_code = str(case_data.get("consultant_code") or "").strip()
        if not consultant_code and "阳光财产保险股份有限公司" in insurance_company_name:
            consultant_code = "08740007"

        preserve_category_text = str(case_data.get("preserve_category") or "诉前保全").strip() or "诉前保全"
        done: dict[str, Any] = {
            "court": self._choose_court(str(case_data.get("court_name") or "")),
            "preserve_type": self._click_radio_in_form_item(["保全类型"], "财产保全")
            or self._click_radio_by_text("财产保全"),
            "preserve_category": self._click_radio_in_form_item(["保全类别"], preserve_category_text)
            or self._click_radio_by_text(preserve_category_text),
            "case_number": self._fill_case_number(case_data),
            "cause": self._fill_case_cause(
                str(case_data.get("cause_of_action") or ""),
                [str(item) for item in (case_data.get("cause_candidates") or [])],
            ),
            "insurance": self._choose_insurance(insurance_company_name),
            "consultant_code": self._fill_consultant_code(consultant_code),
            "amount": self._fill_amount(case_data.get("preserve_amount")),
            "identity": self._click_radio_in_form_item(["提交人身份"], "律师") or self._click_radio_by_text("律师"),
        }

        apply_btn = self._submit_apply_and_wait_g_two()
        self._random_wait(0.8, 1.2)

        g_two_result: dict[str, Any] | None = None
        if "gTwo" in self.page.url:
            g_two_result = self._complete_g_two(case_data)

        upload_result: dict[str, Any] | None = None
        if "gThree" in self.page.url:
            upload_result = self._complete_g_three(case_data)

        self._advance_to_g_five()

        final_url = self.page.url
        success = "gFive" in final_url
        final_errors = self._get_visible_form_errors() if not success else []
        message = "担保流程执行完成（已到预览页，未提交）"
        if not success:
            message = "担保流程已执行，未到 gFive，请人工确认页面"
            if final_errors:
                message = f"{message}；当前错误：{'；'.join(final_errors[:3])}"

        return {
            "success": success,
            "message": message,
            "url": final_url,
            "stage": "gFive" if success else "unknown",
            "filled": done,
            "apply_clicked": apply_btn,
            "g_two_result": g_two_result,
            "upload_result": upload_result,
            "final_errors": final_errors,
        }

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
                    self._random_wait(1.0, 1.6)
                    continue

                ready = self._wait_court_options_ready(candidates=candidates, timeout_ms=self.MAX_SLOW_WAIT_MS)
                if not ready:
                    self._close_popovers()
                    self._random_wait(1.2, 2.0)
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
                    self._close_popovers()
                    self._random_wait(1.2, 2.0)
                    continue

                self._random_wait(0.8, 1.3)
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
                    self._close_popovers()
                    return True

                self._close_popovers()
                self._random_wait(1.0, 1.8)

        logger.warning("court_guarantee_court_not_stable", extra={"target_name": target_name})
        return False

    def _click_radio_in_form_item(self, label_keywords: list[str], option_text: str) -> bool:
        cleaned_option = str(option_text or "").strip()
        cleaned_keywords = [str(keyword).strip() for keyword in label_keywords if str(keyword).strip()]
        if not cleaned_option or not cleaned_keywords:
            return False

        ready = self._wait_form_item_option_ready(
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
                self._random_wait(0.6, 1.1)
                return True
            self._random_wait(1.0, 1.6)

        return False

    def _click_radio_by_text(self, text: str) -> bool:
        option = self.page.locator("label, .el-radio-wrapper").filter(has_text=text).first
        if option.count() == 0:
            return False
        try:
            option.click(timeout=3000)
        except Exception:
            option.click(force=True)
        self._random_wait(0.3, 0.6)
        return True

    def _fill_case_number(self, case_data: dict[str, Any]) -> dict[str, bool]:
        result = {"case_type": False, "year": False, "court_code": False, "type_code": False, "seq": False}

        case_type_input = self.page.locator("input[placeholder*='案件类型']").first
        if case_type_input.count() > 0:
            case_type_input.click()
            self._random_wait(0.4, 0.7)
            result["case_type"] = self._choose_dropdown_item("民事")
            self._close_popovers()

        year_input = self.page.locator("input[placeholder='年份']").first
        year = str(case_data.get("case_year") or "")
        if year_input.count() > 0 and year:
            year_input.click()
            self._random_wait(0.4, 0.7)
            result["year"] = self._choose_dropdown_item(year)
            self._close_popovers()

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

    def _complete_g_two(self, case_data: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {"dialogs": [], "next_clicked": None, "errors_after_next": [], "ready": False}
        result["ready"] = self._wait_for_g_two_ready()

        respondent_sources = [item for item in (case_data.get("respondents") or []) if isinstance(item, dict)]
        if not respondent_sources:
            respondent_sources = [case_data.get("respondent") or {}]

        property_clue_sources = [item for item in (case_data.get("property_clues") or []) if isinstance(item, dict)]
        if not property_clue_sources and isinstance(case_data.get("property_clue"), dict):
            property_clue_sources = [case_data.get("property_clue") or {}]

        targets = [
            ("applicant", 0, ["申请人"], self._build_party_dialog_defaults(case_data.get("applicant") or {})),
            *[
                ("respondent", 1, ["被申请人"], self._build_party_dialog_defaults(source))
                for source in respondent_sources
            ],
            (
                "plaintiff_agent",
                2,
                ["原告代理人", "代理人"],
                self._build_agent_dialog_defaults(case_data.get("plaintiff_agent") or case_data.get("applicant") or {}),
            ),
            *[
                (
                    "property_clue",
                    3,
                    ["财产线索", "财产"],
                    self._build_party_dialog_defaults(
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
                self._random_wait(0.5, 0.8)

            step["opened"] = opened
            if not opened:
                result["dialogs"].append(step)
                continue

            self._random_wait(0.8, 1.2)
            if target in {"applicant", "respondent"}:
                step["party_type_selected"] = self._choose_party_type_in_dialog(defaults)
            selected = self._fill_dialog_select_fields(defaults, target)
            dated = self._fill_dialog_date_fields()
            filled = self._fill_dialog_required_fields(defaults)
            playwright_filled = self._fill_dialog_fields_with_playwright(defaults, target)
            step["filled"] = [*selected, *dated, *filled, *playwright_filled]
            step["saved"] = self._click_first_enabled_button(["确定", "保存", "提交", "完成"])
            self._random_wait(0.8, 1.2)

            errors = self._get_visible_form_errors()
            if target == "property_clue" and any(
                ("请选择省份" in err) or ("请选择财产所有人" in err) for err in errors
            ):
                step["property_clue_retry"] = self._retry_property_clue_save_on_province_error(defaults)
                self._random_wait(0.5, 0.8)
                errors = self._get_visible_form_errors()

            step["errors"] = errors
            if errors:
                step["cancelled"] = bool(self._click_first_enabled_button(["取消", "关闭", "返回"]))
                self._random_wait(0.6, 0.9)

            result["dialogs"].append(step)

        result["next_clicked"] = self._click_first_enabled_button(["下一步", "保存并下一步"])
        self._random_wait(2, 3)
        result["errors_after_next"] = self._get_visible_form_errors()
        return result

    def _submit_apply_and_wait_g_two(self, retries: int = 4) -> str | None:
        last_clicked: str | None = None
        for _ in range(retries):
            last_clicked = self._click_first_enabled_button(["申请担保", "下一步", "保存并下一步"])
            if not last_clicked:
                self._random_wait(0.6, 0.9)
                continue

            for _ in range(10):
                if "gTwo" in self.page.url:
                    return last_clicked
                self._random_wait(0.25, 0.45)

            self._click_first_enabled_button(["确定", "知道了", "我知道了", "继续"])
            self._close_popovers()
            self._random_wait(0.5, 0.8)

        return last_clicked

    def _complete_g_three(self, case_data: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {"uploaded": 0, "next_clicked": None, "uploads": []}
        file_paths = [str(p) for p in case_data.get("material_paths") or [] if str(p)]
        if not file_paths:
            return result

        used: set[str] = set()

        def _pick_path(keyword_groups: list[list[str]]) -> str | None:
            for keywords in keyword_groups:
                for path in file_paths:
                    if path in used:
                        continue
                    filename = path.rsplit("/", 1)[-1]
                    if any(keyword in filename for keyword in keywords):
                        return path
            for path in file_paths:
                if path not in used:
                    return path
            return None

        file_inputs = self.page.locator("input[type='file']")
        total_inputs = min(file_inputs.count(), 10)
        for i in range(total_inputs):
            current = file_inputs.nth(i)
            try:
                label_text = str(
                    self.page.evaluate(
                        r"""(el) => {
                            const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
                            let node = el;
                            for (let depth = 0; depth < 8 && node; depth += 1) {
                                const text = norm(node.innerText || '');
                                if (text) return text;
                                node = node.parentElement;
                            }
                            return '';
                        }""",
                        current.element_handle(),
                    )
                    or ""
                )
            except Exception:
                label_text = ""

            chosen_files: list[str] = []
            if "保全申请" in label_text:
                picked = _pick_path([["财产保全申请书", "保全申请书"], ["申请书"]])
                if picked:
                    chosen_files = [picked]
            elif "起诉" in label_text:
                picked = _pick_path([["起诉状", "起诉书"], ["起诉"]])
                if picked:
                    chosen_files = [picked]
            elif "受理" in label_text or "立案" in label_text:
                picked = _pick_path([["受理案件通知书", "受理通知书", "立案受理通知书", "立案通知书", "立案通知"]])
                if picked:
                    chosen_files = [picked]
            elif "案件证据" in label_text:
                picked = _pick_path([["证据"], ["明细", "清单"]])
                if picked:
                    chosen_files = [picked]
            elif "申请人-" in label_text or "被申请人-" in label_text or "身份证明" in label_text:
                if "申请人-" in label_text and "-法人" in label_text:
                    applicant_license = _pick_path([["营业执照"]])
                    applicant_legal_id = _pick_path([["法定代表人身份证明", "身份证明书", "法人身份证明", "身份证"]])
                    chosen_files = [path for path in [applicant_license, applicant_legal_id] if path]
                elif "被申请人-" in label_text and "-自然人" in label_text:
                    respondent_name = ""
                    match = re.search(r"被申请人-(.*?)-自然人", label_text)
                    if match:
                        respondent_name = str(match.group(1) or "").strip()

                    natural_identity = ""
                    for path in file_paths:
                        if path in used:
                            continue
                        filename = path.rsplit("/", 1)[-1]
                        if "法定代表人" in filename:
                            continue
                        if "身份证" not in filename and "身份证明" not in filename:
                            continue
                        if respondent_name and respondent_name not in filename:
                            continue
                        natural_identity = path
                        break

                    if natural_identity:
                        chosen_files = [natural_identity]
                else:
                    picked = _pick_path([["身份证明", "身份证"], ["营业执照"], ["授权委托书", "所函"]])
                    if picked:
                        chosen_files = [picked]
            elif "代理人" in label_text:
                picked = _pick_path([["所函", "授权委托书", "律师证", "执业证"], ["身份证明", "身份证"]])
                if picked:
                    chosen_files = [picked]
            elif "证据" in label_text:
                picked = _pick_path([["证据"], ["明细", "清单"]])
                if picked:
                    chosen_files = [picked]
            elif "其他" in label_text:
                picked = _pick_path([["其他", "保函", "担保函"]])
                if picked:
                    chosen_files = [picked]
            else:
                picked = _pick_path([[]])
                if picked:
                    chosen_files = [picked]

            if not chosen_files:
                continue

            upload_payload: str | list[str] = chosen_files if len(chosen_files) > 1 else chosen_files[0]
            try:
                current.set_input_files(upload_payload)
                used.update(chosen_files)
                result["uploaded"] = int(result["uploaded"]) + 1
                if len(chosen_files) > 1:
                    result["uploads"].append(
                        {
                            "index": i,
                            "label": label_text[:80],
                            "files": [path.rsplit("/", 1)[-1] for path in chosen_files],
                        }
                    )
                else:
                    result["uploads"].append(
                        {"index": i, "label": label_text[:80], "file": chosen_files[0].rsplit("/", 1)[-1]}
                    )
                self._wait_upload_idle(timeout_ms=90000)
                self._random_wait(1.8, 2.8)
            except Exception:
                continue

        complaint_path = next(
            (
                path
                for path in file_paths
                if (
                    "起诉状" in path.rsplit("/", 1)[-1]
                    or "起诉书" in path.rsplit("/", 1)[-1]
                    or "起诉" in path.rsplit("/", 1)[-1]
                )
            ),
            file_paths[0],
        )

        for _ in range(12):
            self._wait_upload_idle(timeout_ms=90000)
            result["next_clicked"] = self._click_first_enabled_button(["下一步", "保存并下一步"])
            self._random_wait(1.4, 2.2)
            if "gFour" in self.page.url or "gFive" in self.page.url:
                break

            errors = self._get_visible_form_errors()
            if any("请上传起诉" in err for err in errors):
                for j in range(total_inputs):
                    candidate = file_inputs.nth(j)
                    try:
                        label_text = str(
                            self.page.evaluate(
                                r"""(el) => {
                                    let node = el;
                                    for (let depth = 0; depth < 8 && node; depth += 1) {
                                        const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                        if (text) return text;
                                        node = node.parentElement;
                                    }
                                    return '';
                                }""",
                                candidate.element_handle(),
                            )
                            or ""
                        )
                    except Exception:
                        label_text = ""
                    if "起诉" not in label_text:
                        continue
                    try:
                        candidate.set_input_files(complaint_path)
                        result["uploads"].append(
                            {
                                "index": j,
                                "label": label_text[:80],
                                "file": complaint_path.rsplit("/", 1)[-1],
                                "retry": True,
                            }
                        )
                        self._random_wait(1.8, 2.4)
                    except Exception:
                        continue

            if any("身份证明材料" in err for err in errors):
                identity_paths: list[str] = []
                legal_identity = _pick_path([["法定代表人身份证明", "身份证明书", "身份证明", "身份证"]])
                business_license = _pick_path([["营业执照"]])
                if legal_identity:
                    identity_paths.append(legal_identity)
                if business_license and business_license not in identity_paths:
                    identity_paths.append(business_license)

                target_hints: list[str] = []
                for err in errors:
                    match = re.search(r"请上传【(.+?)】的身份证明材料", err)
                    if not match:
                        continue
                    hint = str(match.group(1) or "").strip()
                    if hint and hint not in target_hints:
                        target_hints.append(hint)

                if identity_paths:
                    for j in range(total_inputs):
                        candidate = file_inputs.nth(j)
                        try:
                            label_text = str(
                                self.page.evaluate(
                                    r"""(el) => {
                                        let node = el;
                                        for (let depth = 0; depth < 8 && node; depth += 1) {
                                            const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                            if (text) return text;
                                            node = node.parentElement;
                                        }
                                        return '';
                                    }""",
                                    candidate.element_handle(),
                                )
                                or ""
                            )
                        except Exception:
                            label_text = ""
                        if "身份证明" not in label_text:
                            continue
                        if target_hints and not any(hint in label_text for hint in target_hints):
                            continue
                        try:
                            candidate.set_input_files(identity_paths)
                            result["uploads"].append(
                                {
                                    "index": j,
                                    "label": label_text[:80],
                                    "files": [path.rsplit("/", 1)[-1] for path in identity_paths],
                                    "retry": True,
                                    "reason": "identity_material",
                                }
                            )
                            self._random_wait(2.0, 2.8)
                        except Exception:
                            for single_path in identity_paths:
                                try:
                                    candidate.set_input_files(single_path)
                                    result["uploads"].append(
                                        {
                                            "index": j,
                                            "label": label_text[:80],
                                            "file": single_path.rsplit("/", 1)[-1],
                                            "retry": True,
                                            "reason": "identity_material_fallback",
                                        }
                                    )
                                    self._random_wait(1.6, 2.2)
                                    break
                                except Exception:
                                    continue

            if any("请上传" in err or "正在进行上传" in err or "当前正在进行上传操作" in err for err in errors):
                self._wait_upload_idle(timeout_ms=120000)
                self._random_wait(2.2, 3.2)

        final_upload_errors = self._get_visible_form_errors()
        if any("身份证明材料" in err for err in final_upload_errors):
            legal_identity = _pick_path([["法定代表人身份证明", "身份证明书", "身份证明", "身份证"]])
            business_license = _pick_path([["营业执照"]])
            retry_files: list[str] = []
            if legal_identity:
                retry_files.append(legal_identity)
            if business_license and business_license not in retry_files:
                retry_files.append(business_license)

            if retry_files:
                for j in range(total_inputs):
                    candidate = file_inputs.nth(j)
                    try:
                        label_text = str(
                            self.page.evaluate(
                                r"""(el) => {
                                    let node = el;
                                    for (let depth = 0; depth < 8 && node; depth += 1) {
                                        const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                        if (text) return text;
                                        node = node.parentElement;
                                    }
                                    return '';
                                }""",
                                candidate.element_handle(),
                            )
                            or ""
                        )
                    except Exception:
                        label_text = ""

                    if "申请人-" not in label_text or "-法人" not in label_text:
                        continue

                    try:
                        candidate.set_input_files(retry_files)
                        result["uploads"].append(
                            {
                                "index": j,
                                "label": label_text[:80],
                                "files": [path.rsplit("/", 1)[-1] for path in retry_files],
                                "retry": True,
                                "reason": "identity_material_final_retry",
                            }
                        )
                    except Exception:
                        for single_path in retry_files:
                            try:
                                candidate.set_input_files(single_path)
                                result["uploads"].append(
                                    {
                                        "index": j,
                                        "label": label_text[:80],
                                        "file": single_path.rsplit("/", 1)[-1],
                                        "retry": True,
                                        "reason": "identity_material_final_retry_single",
                                    }
                                )
                                break
                            except Exception:
                                continue

                for _ in range(4):
                    result["next_clicked"] = self._click_first_enabled_button(["下一步", "保存并下一步"])
                    self._random_wait(1.2, 1.8)
                    if "gFour" in self.page.url or "gFive" in self.page.url:
                        break

        return result

    def _retry_identity_material_upload_in_g_three(self) -> bool:
        def _pick_path(keyword_groups: list[list[str]]) -> str | None:
            for keywords in keyword_groups:
                for path in self._material_paths:
                    filename = path.rsplit("/", 1)[-1]
                    if any(keyword in filename for keyword in keywords):
                        return path
            return None

        legal_identity = _pick_path([["法定代表人身份证明", "身份证明书", "身份证明", "身份证"]])
        business_license = _pick_path([["营业执照"]])
        retry_files: list[str] = []
        if legal_identity:
            retry_files.append(legal_identity)
        if business_license and business_license not in retry_files:
            retry_files.append(business_license)
        if not retry_files:
            return False

        uploaded = False
        file_inputs = self.page.locator("input[type='file']")
        for i in range(file_inputs.count()):
            candidate = file_inputs.nth(i)
            try:
                label_text = str(
                    self.page.evaluate(
                        r"""(el) => {
                            let node = el;
                            for (let depth = 0; depth < 8 && node; depth += 1) {
                                const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
                                if (text) return text;
                                node = node.parentElement;
                            }
                            return '';
                        }""",
                        candidate.element_handle(),
                    )
                    or ""
                )
            except Exception:
                label_text = ""

            if "申请人-" not in label_text or "-法人" not in label_text:
                continue

            try:
                candidate.set_input_files(retry_files)
                uploaded = True
                self._wait_upload_idle(timeout_ms=90000)
                self._random_wait(2.0, 2.8)
            except Exception:
                for single_path in retry_files:
                    try:
                        candidate.set_input_files(single_path)
                        uploaded = True
                        self._wait_upload_idle(timeout_ms=90000)
                        self._random_wait(1.8, 2.4)
                        break
                    except Exception:
                        continue

        return uploaded

    def _normalize_party_type(self, raw_party_type: Any) -> str:
        value = str(raw_party_type or "").strip().lower()
        if value in {"natural", "person", "individual"}:
            return "natural"
        if value in {"legal", "corp", "company", "enterprise", "organization", "org"}:
            return "legal"
        if value in {"non_legal_org", "nonlegal", "non_legal", "other_org"}:
            return "non_legal_org"
        return "natural"

    def _build_party_dialog_defaults(
        self,
        party: dict[str, Any],
        *,
        is_property_clue: bool = False,
        property_clue_data: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        name = str(party.get("name") or "").strip() or "张三"
        party_type = self._normalize_party_type(party.get("party_type") or "natural")
        is_natural = party_type == "natural"

        id_number = str(party.get("id_number") or "").strip()
        if not id_number:
            id_number = self.DEFAULT_NATURAL_ID_NUMBER if is_natural else self.DEFAULT_LEGAL_ID_NUMBER

        legal_representative = str(party.get("legal_representative") or "").strip() or "张三"
        legal_representative_id_number = (
            str(party.get("legal_representative_id_number") or "").strip() or self.DEFAULT_NATURAL_ID_NUMBER
        )

        defaults = {
            "party_type": party_type,
            "name": name,
            "unit_name": name,
            "owner_name": name,
            "id_number": id_number,
            "license_number": id_number,
            "phone": str(party.get("phone") or "").strip(),
            "telephone_area_code": "",
            "telephone_number": "",
            "telephone_extension": "",
            "birth_date": "1990-01-01",
            "age": "36",
            "gender": "男性",
            "address": str(party.get("address") or "").strip() or "广东省广州市天河区测试地址1号",
            "unit_address": str(party.get("address") or "").strip() or "广东省广州市天河区测试地址1号",
            "legal_representative": legal_representative,
            "legal_representative_id_number": legal_representative_id_number,
            "principal": legal_representative,
            "unit_nature": "企业",
            "property_type": "其他",
            "property_info": "",
            "property_location": "",
            "property_province": "",
            "property_cert_no": "",
            "property_value": "",
        }
        if is_property_clue:
            clue_data = property_clue_data or {}
            defaults["party_type"] = "property"
            defaults["owner_name"] = str(clue_data.get("owner_name") or name).strip() or name
            defaults["property_type"] = str(clue_data.get("property_type") or "其他").strip() or "其他"
            defaults["property_info"] = (
                str(clue_data.get("property_info") or "").strip() or f"{defaults['owner_name']}名下财产线索"
            )
            defaults["property_location"] = str(
                clue_data.get("property_location") or defaults.get("address") or ""
            ).strip()
            defaults["property_province"] = str(clue_data.get("property_province") or "").strip()
            defaults["property_cert_no"] = str(clue_data.get("property_cert_no") or "").strip()
            defaults["property_value"] = str(clue_data.get("property_value") or "").strip() or "300000"
        return defaults

    def _build_agent_dialog_defaults(self, source: dict[str, Any]) -> dict[str, str]:
        name = str(source.get("name") or "").strip() or "张三"
        id_number = str(source.get("id_number") or "").strip() or self.DEFAULT_NATURAL_ID_NUMBER
        phone = str(source.get("phone") or "").strip()
        return {
            "party_type": "agent",
            "name": name,
            "id_number": id_number,
            "phone": phone,
            "telephone_area_code": "",
            "telephone_number": "",
            "telephone_extension": "",
            "law_firm": str(source.get("law_firm") or "").strip(),
            "license_number": str(source.get("license_number") or "").strip(),
            "agent_type": "执业律师",
            "principal_party_name": str(source.get("name") or "").strip() or name,
            "gender": "男性",
        }

    def _advance_to_g_five(self) -> None:
        for _ in range(8):
            if "gFive" in self.page.url:
                return

            if "gThree" in self.page.url:
                errors = self._get_visible_form_errors()
                if any("身份证明材料" in err for err in errors):
                    self._retry_identity_material_upload_in_g_three()
                    self._random_wait(1.4, 2.0)

            self._click_first_enabled_button(["下一步", "保存并下一步", "暂存"])
            self._random_wait(1.2, 1.8)

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

    def _click_first_enabled_button(self, names: list[str]) -> str | None:
        for name in names:
            selectors = [
                self.page.get_by_role("button", name=name),
                self.page.locator("button, [role='button'], .el-button").filter(has_text=name),
                self.page.locator(f"xpath=//*[normalize-space(text())='{name}']"),
            ]
            for selector in selectors:
                if selector.count() == 0:
                    continue
                for i in range(selector.count()):
                    button = selector.nth(i)
                    try:
                        if not button.is_visible():
                            continue
                        button.click(timeout=3000)
                        return name
                    except Exception:
                        try:
                            button.click(force=True, timeout=3000)
                            return name
                        except Exception:
                            continue
        return None

    def _wait_for_g_two_ready(self, retries: int = 12) -> bool:
        for _ in range(retries):
            if "gTwo" not in self.page.url:
                self._random_wait(0.3, 0.5)
                continue
            if self.page.locator("xpath=//*[contains(normalize-space(text()),'添加')]").count() > 0:
                return True
            self._random_wait(0.4, 0.7)
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

    def _choose_party_type_in_dialog(self, defaults: dict[str, str]) -> bool:
        party_type = self._normalize_party_type(defaults.get("party_type") or "natural")
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
                const dialog = [...document.querySelectorAll('.el-dialog, .el-dialog__wrapper')]
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
        self._random_wait(0.2, 0.4)
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

                const dialog = [...document.querySelectorAll('.el-dialog, .el-dialog__wrapper')]
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
        self._random_wait(0.2, 0.4)
        self._close_popovers()
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
                const dialog = [...document.querySelectorAll('.el-dialog, .el-dialog__wrapper')]
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
                    [['手机号码'], defaults.phone || ''],
                    [['经常居住地', '住所地', '地址'], defaults.address || '广东省广州市天河区测试地址1号'],
                ];
                const legalMap = [
                    [['单位名称', '名称'], defaults.unit_name || defaults.name || '测试公司'],
                    [['证照号码', '统一社会信用代码'], defaults.license_number || defaults.id_number || '91440101MA59TEST8X'],
                    [['法定代表人'], defaults.legal_representative || '张三'],
                    [['主要负责人'], defaults.principal || defaults.legal_representative || '张三'],
                    [['手机号码'], defaults.phone || ''],
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
                    [['手机号码'], defaults.phone || ''],
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
                    [['手机号码'], defaults.phone || ''],
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

                const dialog = [...document.querySelectorAll('.el-dialog, .el-dialog__wrapper')]
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
            selected_text = self._force_vue_select_by_label(label_keyword, preferred_texts)
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

        normalized_party_type = self._normalize_party_type(defaults.get("party_type") or "natural")
        if target in {"applicant", "respondent"} and normalized_party_type in {"legal", "non_legal_org"}:
            selected_unit_nature = self._force_vue_select_by_label(
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
                    const dialog = [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper')].filter(isVisible).slice(-1)[0] || document;
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
            selected_property_type = self._force_vue_select_by_label(
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
                    const dialog = [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper')].filter(isVisible).slice(-1)[0] || document;
                    const provinceInputs = [...dialog.querySelectorAll('input')]
                        .filter((el) => isVisible(el) && !el.disabled && ((el.placeholder || '').includes('省') || (el.parentElement?.innerText || '').includes('省份')));
                    for (const input of provinceInputs) {
                        if (!(input.value || '').trim()) setValue(input, province || '广东省');
                    }
                }""",
                defaults.get("property_province") or "广东省",
            )

            cascaders = self.page.locator(".el-dialog .el-cascader")
            if cascaders.count() > 0:
                try:
                    cascaders.first.click(force=True, timeout=2000)
                    self._random_wait(0.2, 0.4)
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
            type_inputs = self.page.locator(".el-dialog input[placeholder='请选择财产类型']")
            for i in range(type_inputs.count()):
                field = type_inputs.nth(i)
                if not field.is_visible() or field.is_disabled():
                    continue
                selected = False
                for retry in range(4):
                    reopened = self._reopen_and_search_dropdown_input(
                        field,
                        "其他",
                        force_reset=retry > 0,
                        open_timeout_ms=2500,
                        submit_enter=True,
                    )
                    if not reopened:
                        self._random_wait(0.3, 0.6)
                        continue
                    self._wait_select_options_ready(candidates=["其他"], timeout_ms=min(self.MAX_SLOW_WAIT_MS, 45000))
                    selected = self._choose_dropdown_item("其他")
                    if selected:
                        break
                    self._close_popovers()
                    self._random_wait(0.5, 0.8)
                if selected:
                    updates.append("财产类型=其他")
                    break
        except Exception:
            pass

        try:
            owner_inputs = self.page.locator(".el-dialog input[placeholder='请选择财产所有人']")
            for i in range(owner_inputs.count()):
                field = owner_inputs.nth(i)
                if not field.is_visible() or field.is_disabled():
                    continue
                selected = False
                for retry in range(4):
                    reopened = self._reopen_and_search_dropdown_input(
                        field,
                        owner_name,
                        force_reset=retry > 0,
                        open_timeout_ms=2500,
                        submit_enter=True,
                    )
                    if not reopened:
                        self._random_wait(0.4, 0.8)
                        continue
                    self._wait_select_options_ready(
                        candidates=[owner_name], timeout_ms=min(self.MAX_SLOW_WAIT_MS, 60000)
                    )
                    selected = self._choose_dropdown_item(owner_name)
                    if not selected:
                        selected = self._choose_dropdown_item("")
                    if selected:
                        break
                    self._close_popovers()
                    self._random_wait(0.6, 1.0)
                if selected:
                    updates.append("财产所有人=已选")
                    break
        except Exception:
            pass

        try:
            province_inputs = self.page.locator(".el-dialog .fd-sf input.el-input__inner")
            if province_inputs.count() > 0:
                field = province_inputs.first
                if field.is_visible() and not field.is_disabled():
                    selected = False
                    for retry in range(4):
                        reopened = self._reopen_and_search_dropdown_input(
                            field,
                            province_keyword if retry < 3 else province_name,
                            force_reset=retry > 0,
                            open_timeout_ms=2500,
                            submit_enter=True,
                        )
                        if not reopened:
                            self._random_wait(0.4, 0.8)
                            continue
                        self._wait_select_options_ready(
                            candidates=[province_keyword, province_name],
                            timeout_ms=min(self.MAX_SLOW_WAIT_MS, 60000),
                        )
                        selected = self._choose_dropdown_item(province_keyword)
                        if not selected:
                            selected = self._choose_dropdown_item(province_name)
                        if not selected:
                            selected = self._choose_dropdown_item("")
                        if selected:
                            break
                        self._close_popovers()
                        self._random_wait(0.5, 0.9)
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

                const dialog = [...document.querySelectorAll('.el-dialog,.el-dialog__wrapper')].filter(isVisible).slice(-1)[0] || document;
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
        self._close_popovers()
        return updates

    def _retry_property_clue_save_on_province_error(self, defaults: dict[str, str]) -> bool:
        for _ in range(4):
            try:
                self._fill_property_clue_dialog_v15(defaults)

                self._random_wait(0.2, 0.4)
                self._click_first_enabled_button(["保存", "确定"])
                self._random_wait(0.6, 0.9)

                errors = self._get_visible_form_errors()
                has_required_select_error = any(("请选择省份" in err) or ("请选择财产所有人" in err) for err in errors)
                if not has_required_select_error:
                    return True
            except Exception:
                continue
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

    def _wait_tree_options_ready(self, *, candidates: list[str], timeout_ms: int) -> bool:
        deadline = time.time() + max(timeout_ms, 1000) / 1000
        normalized_candidates = [str(item).strip() for item in candidates if str(item).strip()]

        while time.time() < deadline:
            ready = bool(
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
                            .map((node) => norm(node.innerText || ''))
                            .filter((text) => text && !text.includes('暂无数据'));

                        if (nodes.length === 0) return false;
                        if (targets.length === 0) return true;

                        return targets.some((target) =>
                            nodes.some((text) => text === target || text.endsWith(target) || text.includes(target))
                        );
                    }""",
                    normalized_candidates,
                )
            )
            if ready:
                return True
            self._random_wait(
                self.DEFAULT_POLL_MS / 1000,
                (self.DEFAULT_POLL_MS + 800) / 1000,
            )

        return False

    def _wait_select_options_ready(self, *, candidates: list[str], timeout_ms: int) -> bool:
        deadline = time.time() + max(timeout_ms, 1000) / 1000
        normalized_candidates = [str(item).strip() for item in candidates if str(item).strip()]

        while time.time() < deadline:
            ready = bool(
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
                        const options = [...document.querySelectorAll('.el-select-dropdown__item, .el-option, [role="option"], .el-popper li')]
                            .filter((node) => isVisible(node) && !node.classList.contains('is-disabled'))
                            .map((node) => norm(node.innerText || ''))
                            .filter((text) => text && !text.includes('暂无数据'));

                        if (options.length === 0) return false;
                        if (targets.length === 0) return true;

                        return targets.some((target) =>
                            options.some((text) => text === target || text.includes(target) || target.includes(text))
                        );
                    }""",
                    normalized_candidates,
                )
            )
            if ready:
                return True
            self._random_wait(
                self.DEFAULT_POLL_MS / 1000,
                (self.DEFAULT_POLL_MS + 800) / 1000,
            )

        return False

    def _wait_court_options_ready(self, *, candidates: list[str], timeout_ms: int) -> bool:
        deadline = time.time() + max(timeout_ms, 1000) / 1000
        normalized_candidates = [str(item).strip() for item in candidates if str(item).strip()]

        while time.time() < deadline:
            ready = bool(
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
                            .map((node) => norm(node.innerText || ''))
                            .filter((text) => text && !text.includes('暂无数据'));

                        if (nodes.length === 0) return false;
                        if (targets.length === 0) return true;

                        return targets.some((target) =>
                            nodes.some((text) => text === target || text.endsWith(target) || text.includes(target))
                        );
                    }""",
                    normalized_candidates,
                )
            )
            if ready:
                return True
            self._random_wait(
                self.DEFAULT_POLL_MS / 1000,
                (self.DEFAULT_POLL_MS + 800) / 1000,
            )

        logger.warning("court_guarantee_court_options_wait_timeout", extra={"candidates": normalized_candidates})
        return False

    def _wait_form_item_option_ready(self, *, label_keywords: list[str], option_text: str, timeout_ms: int) -> bool:
        deadline = time.time() + max(timeout_ms, 1000) / 1000
        cleaned_option = str(option_text or "").strip()
        cleaned_keywords = [str(keyword).strip() for keyword in label_keywords if str(keyword).strip()]

        while time.time() < deadline:
            ready = bool(
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

                            const options = [...item.querySelectorAll('label, .el-radio, .el-radio-wrapper, .el-radio-button, .el-radio-button__inner, span, div')]
                                .filter((el) => isVisible(el))
                                .map((el) => norm(el.innerText || ''))
                                .filter(Boolean);
                            if (options.length === 0) continue;
                            if (!option) return true;
                            if (options.some((text) => text === option || text.includes(option))) return true;
                        }
                        return false;
                    }""",
                    {"keywords": cleaned_keywords, "option": cleaned_option},
                )
            )
            if ready:
                return True
            self._random_wait(
                self.DEFAULT_POLL_MS / 1000,
                (self.DEFAULT_POLL_MS + 800) / 1000,
            )

        logger.warning(
            "court_guarantee_form_item_wait_timeout",
            extra={"label_keywords": cleaned_keywords, "option_text": cleaned_option},
        )
        return False

    def _wait_upload_idle(self, *, timeout_ms: int = 90000) -> bool:
        deadline = time.time() + max(timeout_ms, 1000) / 1000
        while time.time() < deadline:
            uploading = bool(
                self.page.evaluate(
                    r"""() => {
                        const isVisible = (el) => {
                            if (!el) return false;
                            const st = window.getComputedStyle(el);
                            if (st.display === 'none' || st.visibility === 'hidden') return false;
                            const r = el.getBoundingClientRect();
                            return r.width > 1 && r.height > 1;
                        };

                        const busyTexts = ['当前正在进行上传操作', '正在进行上传', '上传中', '上传操作'];
                        const textNodes = [...document.querySelectorAll('.el-message, .el-form-item__error, .el-notification')]
                            .filter((el) => isVisible(el))
                            .map((el) => (el.innerText || '').replace(/\s+/g, ' ').trim())
                            .filter(Boolean);

                        if (textNodes.some((text) => busyTexts.some((busy) => text.includes(busy)))) {
                            return true;
                        }

                        const loadingNodes = [...document.querySelectorAll('.el-loading-mask, .el-icon-loading, .is-loading')]
                            .filter((el) => isVisible(el));
                        return loadingNodes.length > 0;
                    }"""
                )
            )
            if not uploading:
                return True
            self._random_wait(0.9, 1.4)

        return False

    def _get_visible_form_errors(self) -> list[str]:
        errors = self.page.evaluate(
            r"""() => {
                const isVisible = (el) => {
                    const st = window.getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 1 && r.height > 1;
                };
                return [...document.querySelectorAll('.el-form-item__error, .el-message')]
                    .filter(isVisible)
                    .map((el) => (el.innerText || '').trim())
                    .filter(Boolean);
            }"""
        )
        return [str(item) for item in errors]

    def _close_popovers(self) -> None:
        for _ in range(2):
            self.page.keyboard.press("Escape")
            self._random_wait(0.1, 0.2)

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

    @staticmethod
    def parse_case_number(number: str) -> tuple[str, str, str, str]:
        cleaned = str(number or "").replace("（", "(").replace("）", ")").replace("号", "").strip()
        match = re.search(r"\((\d{4})\)([^\d\s]+\d+)\s*([^\d\s]+)\s*(\d+)", cleaned)
        if not match:
            return "", "", "", ""
        return match.group(1), match.group(2), match.group(3), match.group(4)

    @staticmethod
    def _random_wait(min_sec: float = 0.5, max_sec: float = 1.3) -> None:
        time.sleep(random.uniform(min_sec, max_sec))


__all__ = ["CourtZxfwGuaranteeService"]
