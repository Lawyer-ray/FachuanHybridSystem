"""立案流程步骤 1-4：打开案件类型页、法院选择、须知、案由、上传材料。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

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
        logger.info(str("导航到%s立案页"), case_type)

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

        logger.info(str("已打开%s立案页: %s"), case_type, self.page.url)

    def _step1_select_court(self, court_name: str) -> None:
        """搜索并选择受理法院、选择申请人类型。

        采用三层降级策略：
        策略0: 搜索框搜索（最可靠）
        策略1: 直接在页面查找 checklist-text 元素
        策略2: 城市选择 + 法院列表
        """
        logger.info(str("步骤1: 选择受理法院 - %s"), court_name)

        court_selected = False

        # 策略0: 搜索框搜索
        court_selected = self._try_search_court(court_name)

        # 策略1: 直接查找 checklist-text
        if not court_selected:
            logger.warning("搜索框策略失败，尝试直接查找法院元素")
            court_selected = self._try_find_court_direct(court_name)

        # 策略2: 城市选择 + 法院列表
        if not court_selected:
            logger.warning("直接查找失败，尝试城市选择策略")
            court_selected = self._try_select_court_by_city(court_name)

        if not court_selected:
            raise ValueError(f"无法找到法院: {court_name}（三种策略均失败）")

        self._random_wait(1, 2)
        self._handle_popups()

        self.page.locator('.checklist-box:has-text("为他人或公司等组织申请")').click()
        self._random_wait(0.5, 1)

        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(1, 2)

        self._handle_popups()
        logger.info(str("步骤1完成: 已选择法院 %s"), court_name)

    def _try_search_court(self, court_name: str) -> bool:
        """策略0: 通过搜索框搜索法院"""
        try:
            # 尝试多种搜索框定位
            search_input = (
                self.page.locator('input[placeholder*="搜索"]').first or self.page.locator(".uni-input-input").first
            )
            search_input.click()
            self._random_wait(0.3, 0.5)
            search_input.click(click_count=3)
            self._random_wait(0.2, 0.3)
            # 使用法院全名搜索，比短关键词更精确
            search_input.type(court_name, delay=50)
            self._random_wait(0.5, 1)

            self.page.locator("uni-button:has-text('搜索')").click()
            self._random_wait(2, 3)

            # 优先精确匹配，再模糊匹配
            exact = self.page.locator(f'.checklist-box:has-text("{court_name}")')
            if exact.count():
                exact.first.click()
                return True

            # 双向模糊匹配
            items = self.page.locator(".checklist-text")
            for i in range(items.count()):
                text = items.nth(i).text_content() or ""
                if court_name in text or text in court_name:
                    items.nth(i).click()
                    return True

            return False
        except Exception as e:
            logger.debug("搜索框策略异常: %s", e)
            return False

    def _try_find_court_direct(self, court_name: str) -> bool:
        """策略1: 直接在页面查找 checklist-text 元素"""
        try:
            items = self.page.locator(".checklist-text")
            for i in range(items.count()):
                text = items.nth(i).text_content() or ""
                if court_name in text or text in court_name:
                    items.nth(i).click()
                    return True
            return False
        except Exception as e:
            logger.debug("直接查找策略异常: %s", e)
            return False

    def _try_select_court_by_city(self, court_name: str) -> bool:
        """策略2: 先选城市，再在城市下的法院列表中查找"""
        try:
            city_container = self.page.locator(".fd-city-container")
            if not city_container.count():
                return False

            # 从法院名提取城市（去掉"人民法院"后取前缀）
            city_name = court_name.replace("人民法院", "").rstrip("市")
            city_items = self.page.locator(".fd-city-item")
            for i in range(city_items.count()):
                text = city_items.nth(i).text_content() or ""
                if city_name in text or text in city_name:
                    city_items.nth(i).click()
                    self._random_wait(1, 2)
                    break

            # 在法院列表中查找
            items = self.page.locator(".checklist-text")
            for i in range(items.count()):
                text = items.nth(i).text_content() or ""
                if court_name in text or text in court_name:
                    items.nth(i).click()
                    return True

            return False
        except Exception as e:
            logger.debug("城市选择策略异常: %s", e)
            return False

    def _step2_read_notice(self, *, has_prepared_doc: bool = True) -> None:
        """勾选阅读须知，处理弹窗，选择立案方式"""
        logger.info(str("步骤2: 阅读须知"))

        self.page.get_by_text("已阅读同意立案须知内容").click()
        self._random_wait(0.5, 1)

        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(1, 2)

        # 集中处理所有弹窗（要素式立案、智能识别、数字诉讼标志等）
        self._handle_popups()

        if has_prepared_doc:
            self.page.locator(".fd-name:has-text('已准备诉状')").click()
            self._random_wait(1, 2)

        logger.info(str("步骤2完成: 须知已确认"))

    def _step3_select_cause(self, cause_of_action: str) -> None:
        """搜索并选择案由，选择后验证结果"""
        logger.info(str("步骤3: 选择案由 - %s"), cause_of_action)

        self.page.get_by_text("请选择", exact=True).first.click()
        self._random_wait(1, 2)

        search_input = self.page.locator(".fd-search-input .uni-input-input")
        search_input.click()
        self._random_wait(0.3, 0.5)
        search_input.fill(cause_of_action)
        self._random_wait(1, 2)

        # 优先精确匹配 .item-text，再 fallback 到第一个 .fd-item
        exact_match = self.page.locator(f".item-text:has-text('{cause_of_action}')")
        if exact_match.count():
            exact_match.first.click()
        else:
            self.page.locator(".fd-item").first.click()
        self._random_wait(0.5, 1)

        # 验证选择结果
        try:
            selected_area = self.page.locator(".selected-area").first
            if selected_area.count():
                selected_text = selected_area.get_attribute("title") or selected_area.text_content() or ""
                if cause_of_action not in selected_text:
                    logger.warning("案由选择可能不精确: 期望 '%s', 实际 '%s'", cause_of_action, selected_text)
        except Exception:
            pass

        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(1, 2)

        logger.info(str("步骤3完成: 已选择案由 %s"), cause_of_action)

    def _step_exec_select_basis(self, case_data: dict[str, Any]) -> None:
        """申请执行特有：选择执行依据类别和原审案号"""
        logger.info(str("步骤(执行): 选择执行依据"))

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

        logger.info(str("执行依据选择完成: %s, %s"), basis_type, original_case_number)

    def _step4_upload_materials(self, materials: dict[str, list[tuple[str, str]]], *, is_execution: bool) -> None:
        """上传诉讼材料"""
        logger.info(str("步骤4: 上传诉讼材料"))

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

        for idx_str, items in materials.items():
            idx = int(idx_str) if str(idx_str).isdigit() else -1
            if not items:
                continue

            upload_idx = slot_to_index.get(str(idx_str), idx)
            if upload_idx < 0 or (container_count > 0 and upload_idx >= container_count):
                logger.warning("未找到可用上传槽位: slot=%s", idx_str)
                continue

            logger.info("上传材料 %s -> 槽位 %d: %s", idx_str, upload_idx, [Path(f).name for f, _ in items])
            btn = self.page.locator(f'[data-upload-index="{upload_idx}"]').first

            # 等待 toast 遮罩消失（uni-toast 可能长时间遮挡点击）
            mask = self.page.locator(".uni-mask")
            try:
                mask.wait_for(state="hidden", timeout=5000)
            except Exception:
                # 遮罩未消失，强制移除（uni-toast duration 可能极长）
                self.page.evaluate("document.querySelectorAll('.uni-mask').forEach(e => e.remove())")
                self.page.wait_for_timeout(500)

            for item in items:
                file_path, original_name = item if isinstance(item, tuple) else (item, "")
                # 记录上传前文件数
                files_before = self.page.locator(".fd-file-name").count()

                uploaded = False
                for attempt in range(3):
                    with self.page.expect_file_chooser() as fc_info:
                        btn.click()
                    fc_info.value.set_files(file_path)
                    self.page.wait_for_timeout(2000)

                    # 验证上传成功（文件数增加）
                    files_after = self.page.locator(".fd-file-name").count()
                    if files_after > files_before:
                        uploaded = True
                        break
                    logger.warning("文件上传验证失败，重试(%d/3): %s", attempt + 1, Path(file_path).name)
                    self._random_wait(1, 2)

                if not uploaded:
                    logger.error("文件上传失败（3次重试后）: %s", Path(file_path).name)

            logger.info("材料 %s 上传完成", idx_str)

        loading = self.page.locator("text=加载中")
        try:
            loading.wait_for(state="hidden", timeout=90000)
        except Exception:
            pass
        self._random_wait(2, 3)

        # 引入送达地址确认书（一张网新增步骤，按钮可能不存在）
        self._confirm_address_confirmation_book(loading)

        self.page.locator("uni-button:has-text('下一步')").click()
        try:
            loading.wait_for(state="hidden", timeout=90000)
        except Exception:
            pass
        self._random_wait(2, 3)

        logger.info(str("步骤4完成: 材料已上传"))

    def _infer_upload_slot_by_text(self, *, container_text: str, is_execution: bool) -> str | None:
        normalized_text = "".join(str(container_text or "").split()).lower()
        if not normalized_text:
            return None
        rules = self.EXEC_UPLOAD_SLOT_KEYWORDS if is_execution else self.CIVIL_UPLOAD_SLOT_KEYWORDS
        for slot, keywords in rules:
            if any("".join(keyword.split()).lower() in normalized_text for keyword in keywords):
                return slot
        return None

    def _confirm_address_confirmation_book(self, loading: Any) -> None:
        """点击「引入送达地址确认书」，处理弹窗流程：

        1. 选择邮寄送达地址 → 点击「确认生成」
        2. 弹窗切换到签章选择页面：点击签名卡片 → 点击「引入签章」

        弹窗结构（uni-popup fd-import-file-layer）:
          页面1 - 地址确认:
            - 邮寄送达: 选择地址下拉框 (uni-data-tree) + 添加按钮
            - 电子送达: 送达方式复选框（人民法院在线服务默认勾选）
            - 底部: 取消 / 确认生成
          页面2 - 签章选择（确认生成后切换）:
            - 顶部: 引入签章 / 更新签章 按钮
            - 签名卡片列表 (fd-com-card): 版本号 + 签署时间 + 签名图片
        """
        try:
            confirm_book_btn = self.page.get_by_text("引入送达地址确认书")
            confirm_book_btn.wait_for(state="visible", timeout=5000)
        except Exception:
            logger.debug("未发现「引入送达地址确认书」按钮，跳过")
            return

        confirm_book_btn.click()
        logger.info("已点击「引入送达地址确认书」")
        self._random_wait(2, 3)

        # 等待弹窗出现
        try:
            self.page.locator(".uni-popup__wrapper").first.wait_for(state="visible", timeout=10000)
        except Exception:
            logger.warning("送达地址确认书弹窗未出现")
            return

        # 选择邮寄送达地址（如果下拉框存在且有可选项）
        self._select_address_from_popup()
        self._random_wait(1, 2)

        # 点击「确认生成」
        try:
            confirm_gen_btn = self.page.locator(".uni-popup__wrapper uni-button:has-text('确认生成')")
            confirm_gen_btn.wait_for(state="visible", timeout=5000)
            confirm_gen_btn.click()
            logger.info("已点击「确认生成」")
            self._random_wait(3, 5)
            try:
                loading.wait_for(state="hidden", timeout=30000)
            except Exception:
                pass
        except Exception:
            logger.warning("未找到「确认生成」按钮")
            return

        # 签章选择：点击签名卡片 → 引入签章
        self._select_signature_and_import()

    def _select_address_from_popup(self) -> None:
        """在送达地址确认书弹窗中选择邮寄送达地址。"""
        popup = self.page.locator(".uni-popup__wrapper").first
        address_input = popup.locator(".uni-data-tree .input-value")

        if not address_input.count():
            logger.debug("未找到地址下拉框，跳过地址选择")
            return

        try:
            address_input.first.click(timeout=5000)
            self._random_wait(1, 2)
        except Exception:
            logger.debug("无法点击地址下拉框")
            return

        # 尝试选择第一个可用选项
        try:
            option = self.page.locator(".uni-data-tree .uni-data-tree__node-child-text").first
            if option.count() and option.is_visible():
                option.click()
                logger.info("已选择邮寄送达地址")
                self._random_wait(0.5, 1)
                return
        except Exception:
            pass

        # 备选：尝试 .item-text 类型的选项
        try:
            option = self.page.locator(".item-text").first
            if option.count() and option.is_visible():
                option.click()
                logger.info("已选择邮寄送达地址 (item-text)")
                self._random_wait(0.5, 1)
                return
        except Exception:
            pass

        logger.debug("地址下拉框中未找到可选项，跳过地址选择")
        self.page.keyboard.press("Escape")
        self._random_wait(0.5, 1)

    def _select_signature_and_import(self) -> None:
        """在签章选择页面中选择签名并引入。

        确认生成后弹窗切换为签章选择页面：
        - 签名卡片列表 (.fd-com-card)，点击后获得 .fd-com-card-active class
        - 顶部有「引入签章」按钮
        """
        # 等待签名卡片出现
        try:
            self.page.locator(".fd-com-card").first.wait_for(state="visible", timeout=10000)
        except Exception:
            logger.warning("签章选择页面未出现（无签名卡片）")
            return

        # 点击第一张签名卡片选中
        first_card = self.page.locator(".fd-com-card").first
        first_card.click()
        logger.info("已选择签名卡片")
        self._random_wait(1, 2)

        # 点击「引入签章」
        try:
            import_btn = self.page.locator(".uni-popup__wrapper uni-button:has-text('引入签章')")
            import_btn.wait_for(state="visible", timeout=5000)
            import_btn.click()
            logger.info("已点击「引入签章」")
            self._random_wait(3, 5)
        except Exception:
            logger.warning("未找到「引入签章」按钮")
            return

        # 等待弹窗关闭
        try:
            self.page.locator(".uni-popup__wrapper").first.wait_for(state="hidden", timeout=10000)
        except Exception:
            # 弹窗可能已自动关闭
            self._dismiss_address_popup()

    def _dismiss_address_popup(self) -> None:
        """关闭送达地址确认书弹窗（如果仍打开）。"""
        try:
            close_btn = self.page.locator(".uni-popup__wrapper .fd-com-layer-close")
            if close_btn.count() and close_btn.is_visible():
                close_btn.click()
                self._random_wait(1, 2)
        except Exception:
            pass

    @staticmethod
    def _extract_court_keyword(court_name: str) -> str:
        """从法院全名提取搜索关键词"""
        name = court_name.replace("人民法院", "")
        for sep in ("区", "县"):
            if sep in name:
                idx = name.index(sep)
                return name[max(0, idx - 2) : idx + 1]
        return name
