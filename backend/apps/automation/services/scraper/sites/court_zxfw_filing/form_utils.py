"""表单操作工具方法。"""

from __future__ import annotations

import random
import time
from typing import Any

from playwright.sync_api import Page


class FormUtilsMixin:
    """表单操作工具 Mixin，需要子类提供 self.page。"""

    page: Page

    def _dismiss_popup(self) -> None:
        """关闭可能出现的弹窗（如综治中心提示）"""
        close_btn = self.page.locator('uni-button:has-text("关闭")')
        try:
            close_btn.wait_for(state="visible", timeout=3000)
            close_btn.click()
            self._random_wait(0.5, 1)
        except Exception:
            pass

    def _dismiss_popup_by_text(self, button_text: str) -> None:
        """点击弹窗中指定文本的按钮"""
        btn = self.page.locator(f'uni-button:has-text("{button_text}")')
        try:
            btn.wait_for(state="visible", timeout=5000)
            btn.click()
            self._random_wait(1, 2)
        except Exception:
            pass

    def _open_dropdown_by_labels(self, labels: tuple[str, ...], *, required: bool) -> bool:
        for label in labels:
            trigger = self.page.locator(f".uni-forms-item:has(.uni-forms-item__label:has-text('{label}')) .input-value")
            if not trigger.count():
                continue
            try:
                trigger.first.click(timeout=5000)
                self._random_wait(1, 2)
                return True
            except Exception:
                continue

        message = f"未找到下拉字段: labels={labels}"
        if required:
            raise ValueError(message)
        return False

    def _select_dropdown_by_label(
        self,
        label_text: str | tuple[str, ...],
        option_text: str,
        *,
        required: bool = True,
    ) -> bool:
        """通过 label 定位页面级下拉框（非表单内），选择选项"""
        from django.utils.translation import gettext_lazy as _

        labels = (label_text,) if isinstance(label_text, str) else tuple(label_text)
        if not labels:
            return False
        if not self._open_dropdown_by_labels(labels, required=required):
            return False

        option = self.page.locator(f".item-text:has-text('{option_text}')")
        if not option.count() and "人民法院" in str(option_text or ""):
            option = self.page.locator(f".item-text:has-text('{str(option_text).replace('人民法院', '')}')")
        if option.count():
            option.first.click(timeout=5000)
            self._random_wait(0.5, 1)
            return True

        message = f"下拉选项未命中: labels={labels}, option={option_text}"
        if required:
            raise ValueError(message)
        self.page.keyboard.press("Escape")
        self._random_wait(1, 2)
        return False

    def _fill_field(self, label_text: str, value: str) -> None:
        """通过 label 文本定位并填写当前编辑表单中的 input 字段"""
        if not value:
            return
        form = self.page.locator(".fd-wsla-ryxx-box:has(uni-button:has-text('保存'))").first
        inp = form.locator(
            f".uni-forms-item:has(.uni-forms-item__label:has-text('{label_text}')) .uni-input-input"
        ).first
        try:
            inp.fill(value, timeout=5000)
        except Exception:
            return
        self._random_wait(0.3, 0.5)

    def _fill_field_exact(self, label_text: str, value: str) -> None:
        """通过 label 精确匹配填写字段（避免 has-text 的模糊匹配）"""
        if not value:
            return
        found = self.page.evaluate(
            """([label]) => {
                const forms = document.querySelectorAll('.fd-wsla-ryxx-box');
                for (const form of forms) {
                    if (!form.querySelector('uni-button')) continue;
                    const items = form.querySelectorAll('.uni-forms-item');
                    for (const item of items) {
                        const lbl = item.querySelector('.uni-forms-item__label');
                        if (lbl && lbl.textContent.trim() === label) {
                            const input = item.querySelector('.uni-input-input');
                            if (input) {
                                input.setAttribute('data-exact-fill', '1');
                                return true;
                            }
                        }
                    }
                }
                return false;
            }""",
            [label_text],
        )
        if found:
            self.page.locator("[data-exact-fill='1']").fill(value)
            self.page.evaluate("() => document.querySelector('[data-exact-fill]')?.removeAttribute('data-exact-fill')")
        self._random_wait(0.3, 0.5)

    def _select_dropdown(self, label_text: str, option_text: str) -> bool:
        """点击表单内下拉框并选择选项（.item-text 类型）"""
        form = self.page.locator(".fd-wsla-ryxx-box:has(uni-button:has-text('保存'))").first
        try:
            form.locator(
                f".uni-forms-item:has(.uni-forms-item__label:has-text('{label_text}')) .input-value"
            ).first.click(timeout=5000)
        except Exception:
            return False
        self._random_wait(1, 2)
        try:
            self.page.locator(f".item-text:has-text('{option_text}')").first.click(timeout=5000)
        except Exception:
            self.page.keyboard.press("Escape")
            return False
        self._random_wait(0.5, 1)
        return True

    def _select_tree_dropdown(self, label_text: str, option_text: str) -> bool:
        """点击 uni-data-tree 下拉框并选择选项（.fd-item 类型）"""
        form = self.page.locator(".fd-wsla-ryxx-box:has(uni-button:has-text('保存'))").first
        try:
            form.locator(
                f".uni-forms-item:has(.uni-forms-item__label:has-text('{label_text}')) .input-value"
            ).first.click(timeout=5000)
        except Exception:
            return False
        self._random_wait(1, 2)
        try:
            self.page.locator(f".fd-item:has-text('{option_text}')").first.click(timeout=5000)
        except Exception:
            self.page.keyboard.press("Escape")
            return False
        self._random_wait(0.5, 1)
        return True

    def _click_save(self) -> None:
        """点击当前表单的保存按钮"""
        save = self.page.locator("uni-button:has-text('保存')").first
        save.scroll_into_view_if_needed()
        self._random_wait(0.3, 0.5)
        save.click()
        self._random_wait(2, 3)

    def _click_next_step(self) -> None:
        """点击下一步按钮"""
        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(2, 3)

    def _random_wait(self, min_sec: float = 0.5, max_sec: float = 2.0) -> None:
        """随机等待，模拟人工操作"""
        time.sleep(random.uniform(min_sec, max_sec))
