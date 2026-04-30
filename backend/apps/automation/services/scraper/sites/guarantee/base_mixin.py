"""Playwright 等待与 UI 交互工具方法。"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

logger = logging.getLogger("apps.automation")


class GuaranteeBaseMixin:
    """Playwright 等待与 UI 交互工具。"""

    page: Any
    save_debug: bool
    DEFAULT_POLL_MS: int
    MAX_SLOW_WAIT_MS: int

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
    def _random_wait(min_sec: float = 0.5, max_sec: float = 1.3) -> None:
        time.sleep(random.uniform(min_sec, max_sec))
