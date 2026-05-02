"""立案流程步骤 1-4：打开案件类型页、法院选择、须知、案由、上传材料。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from django.utils.translation import gettext_lazy as _
from playwright.sync_api import Page

from .form_utils import FormUtilsMixin

logger = logging.getLogger("apps.automation")


class FilingStepsMixin(FormUtilsMixin):
    """立案步骤 Mixin，需要子类提供 self.page 和类常量。"""

    page: Page
    CASE_TYPE_URL: str
    CIVIL_UPLOAD_SLOT_KEYWORDS: list[tuple[str, tuple[str, ...]]]
    EXEC_UPLOAD_SLOT_KEYWORDS: list[tuple[str, tuple[str, ...]]]

    def _open_case_type_page(self, case_type: str, province_code: str = "440000") -> None:
        """设置省份并从案件类型页点击指定类型（打开新tab）"""
        logger.info(str(_("导航到%s立案页")), case_type)

        self.page.goto(self.CASE_TYPE_URL, timeout=60000, wait_until="domcontentloaded")
        self.page.get_by_text(case_type, exact=True).wait_for(state="visible", timeout=30000)

        current_province = self.page.evaluate("() => localStorage.getItem('provinceId')")
        if current_province != province_code:
            self.page.evaluate(f"() => localStorage.setItem('provinceId', '{province_code}')")
            self.page.reload(wait_until="domcontentloaded")
            self.page.get_by_text(case_type, exact=True).wait_for(state="visible", timeout=30000)

        self._random_wait(1, 2)

        with self.page.context.expect_page() as new_page_info:
            self.page.get_by_text(case_type, exact=True).click()

        new_page = new_page_info.value
        new_page.wait_for_load_state("domcontentloaded")
        new_page.locator("uni-button").first.wait_for(state="visible", timeout=60000)
        self.page = new_page
        self._random_wait(2, 3)

        logger.info(str(_("已打开%s立案页: %s")), case_type, self.page.url)

    def _step1_select_court(self, court_name: str) -> None:
        """搜索并选择受理法院、选择申请人类型"""
        logger.info(str(_("步骤1: 选择受理法院 - %s")), court_name)

        keyword = self._extract_court_keyword(court_name)

        search_input = self.page.locator(".uni-input-input").first
        search_input.click()
        self._random_wait(0.3, 0.5)
        search_input.click(click_count=3)
        self._random_wait(0.2, 0.3)
        search_input.type(keyword, delay=80)
        self._random_wait(0.5, 1)

        self.page.locator("uni-button:has-text('搜索')").click()
        self._random_wait(2, 3)

        self.page.locator(f'.checklist-box:has-text("{court_name}")').first.click()
        self._random_wait(1, 2)

        self._dismiss_popup()

        self.page.locator('.checklist-box:has-text("为他人或公司等组织申请")').click()
        self._random_wait(0.5, 1)

        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(1, 2)

        logger.info(str(_("步骤1完成: 已选择法院 %s")), court_name)

    def _step2_read_notice(self, *, has_prepared_doc: bool = True) -> None:
        """勾选阅读须知，处理弹窗，选择立案方式"""
        logger.info(str(_("步骤2: 阅读须知")))

        self.page.get_by_text("已阅读同意立案须知内容").click()
        self._random_wait(0.5, 1)

        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(1, 2)

        self._dismiss_popup_by_text("不选择要素式立案")
        self._dismiss_popup_by_text("不体验智能识别要素式立案服务")

        if has_prepared_doc:
            self.page.locator(".fd-name:has-text('已准备诉状')").click()
            self._random_wait(1, 2)

        logger.info(str(_("步骤2完成: 须知已确认")))

    def _step3_select_cause(self, cause_of_action: str) -> None:
        """搜索并选择案由"""
        logger.info(str(_("步骤3: 选择案由 - %s")), cause_of_action)

        self.page.get_by_text("请选择", exact=True).first.click()
        self._random_wait(1, 2)

        search_input = self.page.locator(".fd-search-input .uni-input-input")
        search_input.click()
        self._random_wait(0.3, 0.5)
        search_input.fill(cause_of_action)
        self._random_wait(1, 2)

        self.page.locator(".fd-item").first.click()
        self._random_wait(0.5, 1)

        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(1, 2)

        logger.info(str(_("步骤3完成: 已选择案由 %s")), cause_of_action)

    def _step_exec_select_basis(self, case_data: dict[str, Any]) -> None:
        """申请执行特有：选择执行依据类别和原审案号"""
        logger.info(str(_("步骤(执行): 选择执行依据")))

        basis_type = case_data.get("execution_basis_type", "民商")
        original_case_number = case_data.get("original_case_number", "")

        self._select_dropdown_by_label("执行依据类别", basis_type)

        if self._open_dropdown_by_labels(("原审案号", "原审案件号"), required=False):
            matched = self.page.locator(f".item-text:has-text('{original_case_number}')")
            if original_case_number and matched.count() > 0:
                matched.first.click()
            else:
                manual_input = self.page.locator(".item-text:has-text('选择此项手动输入案号')")
                if manual_input.count():
                    manual_input.first.click()
                self._random_wait(1, 2)

                year_match = re.search(r"[（(](\d{4})[）)]", original_case_number)
                year = year_match.group(1) if year_match else ""
                body = re.sub(r"^[（(]\d{4}[）)]\s*", "", original_case_number).rstrip("号")
                if year and self._open_dropdown_by_labels(("输入案号",), required=False):
                    year_option = self.page.locator(f".item-text:has-text('{year}')")
                    if year_option.count():
                        year_option.first.click()
                        self._random_wait(0.5, 1)
                input_locator = self.page.locator(
                    ".uni-forms-item:has(.uni-forms-item__label:has-text('输入案号')) .uni-input-input"
                )
                if input_locator.count():
                    inp = input_locator.first
                    inp.fill(body)
                    self._random_wait(0.3, 0.5)
                    inp.press("Enter")
                    self._random_wait(0.5, 1)

        self._select_dropdown_by_label(
            ("作出执行依据单位", "作出执行依据文书单位", "执行依据单位"),
            case_data.get("court_name", ""),
            required=False,
        )
        self._random_wait(0.5, 1)

        self.page.locator("uni-button:has-text('保存')").click()
        self._random_wait(1, 2)

        try:
            self.page.locator(".uni-modal__btn_primary").wait_for(state="visible", timeout=5000)
            self.page.locator(".uni-modal__btn_primary").click()
        except Exception:
            self._dismiss_popup_by_text("确定")
        self._random_wait(3, 5)

        logger.info(str(_("执行依据选择完成: %s, %s")), basis_type, original_case_number)

    def _step4_upload_materials(self, materials: dict[str, list[str]], *, is_execution: bool) -> None:
        """上传诉讼材料"""
        logger.info(str(_("步骤4: 上传诉讼材料")))

        self.page.evaluate(
            """() => {
            const containers = document.querySelectorAll('.fd-com-upload-grid-container');
            containers.forEach((c, i) => {
                const b = c.querySelector('.fd-btn-add');
                if (b) b.setAttribute('data-upload-index', String(i));
            });
        }"""
        )

        container_meta = self.page.evaluate(
            """() => {
            const containers = Array.from(document.querySelectorAll('.fd-com-upload-grid-container'));
            return containers.map((c, i) => ({
                index: i,
                text: (c.innerText || '').replace(/\\s+/g, '')
            }));
        }"""
        )

        slot_to_index: dict[str, int] = {}
        if isinstance(container_meta, list):
            for item in container_meta:
                if not isinstance(item, dict):
                    continue
                idx = item.get("index")
                if not isinstance(idx, int):
                    continue
                slot = self._infer_upload_slot_by_text(
                    container_text=str(item.get("text") or ""),
                    is_execution=is_execution,
                )
                if slot and slot not in slot_to_index:
                    slot_to_index[slot] = idx

        container_count = len(container_meta) if isinstance(container_meta, list) else 0

        for idx_str, files in materials.items():
            idx = int(idx_str) if str(idx_str).isdigit() else -1
            if not files:
                continue

            upload_idx = slot_to_index.get(str(idx_str), idx)
            if upload_idx < 0 or (container_count > 0 and upload_idx >= container_count):
                logger.warning("未找到可用上传槽位: slot=%s", idx_str)
                continue

            logger.info("上传材料 %s -> 槽位 %d: %s", idx_str, upload_idx, [Path(f).name for f in files])
            btn = self.page.locator(f'[data-upload-index="{upload_idx}"]').first

            for file_path in files:
                with self.page.expect_file_chooser() as fc_info:
                    btn.click()
                fc_info.value.set_files(file_path)
                self.page.wait_for_timeout(2000)

            logger.info("材料 %s 上传完成", idx_str)

        loading = self.page.locator("text=加载中")
        try:
            loading.wait_for(state="hidden", timeout=90000)
        except Exception:
            pass
        self._random_wait(2, 3)

        self.page.locator("uni-button:has-text('下一步')").click()
        try:
            loading.wait_for(state="hidden", timeout=90000)
        except Exception:
            pass
        self._random_wait(2, 3)

        logger.info(str(_("步骤4完成: 材料已上传")))

    def _infer_upload_slot_by_text(self, *, container_text: str, is_execution: bool) -> str | None:
        normalized_text = "".join(str(container_text or "").split()).lower()
        if not normalized_text:
            return None
        rules = self.EXEC_UPLOAD_SLOT_KEYWORDS if is_execution else self.CIVIL_UPLOAD_SLOT_KEYWORDS
        for slot, keywords in rules:
            if any("".join(keyword.split()).lower() in normalized_text for keyword in keywords):
                return slot
        return None

    @staticmethod
    def _extract_court_keyword(court_name: str) -> str:
        """从法院全名提取搜索关键词"""
        name = court_name.replace("人民法院", "")
        for sep in ("区", "县"):
            if sep in name:
                idx = name.index(sep)
                return name[max(0, idx - 2) : idx + 1]
        return name
