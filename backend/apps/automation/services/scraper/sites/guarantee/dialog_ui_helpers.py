"""gTwo 通用 UI 交互 (add_button/party_type/clear/wait)。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("apps.automation")


class GuaranteeDialogUIHelpersMixin:
    """gTwo 对话框的通用 UI 交互辅助方法。"""

    page: Any

    def _wait_for_g_two_ready(self, retries: int = 12) -> bool:
        for _ in range(retries):
            if "gTwo" not in self.page.url:
                self._random_wait(0.3, 0.5)  # type: ignore[attr-defined]
                continue
            if self.page.locator("xpath=//*[contains(normalize-space(text()),'添加')]").count() > 0:
                return True
            self._random_wait(0.4, 0.7)  # type: ignore[attr-defined]
        return "gTwo" in self.page.url

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
