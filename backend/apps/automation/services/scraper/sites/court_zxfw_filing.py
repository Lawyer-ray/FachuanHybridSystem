"""
全国法院"一张网"在线立案服务 (zxfw.court.gov.cn)
负责民事一审在线立案的全流程自动化
"""

import logging
import random
import time
from pathlib import Path
from typing import Any

from django.utils.translation import gettext_lazy as _
from playwright.sync_api import Page

logger = logging.getLogger("apps.automation")


class CourtZxfwFilingService:
    """
    全国法院"一张网"在线立案服务

    前置条件: 需要已登录的 Page 对象（由 CourtZxfwService.login() 完成）

    立案流程（6步）:
    1. 选择受理法院
    2. 阅读须知
    3. 选择立案案由
    4. 上传诉讼材料
    5. 完善案件信息
    6. 预览和提交
    """

    BASE_URL = "https://zxfw.court.gov.cn/zxfw"
    CASE_TYPE_URL = f"{BASE_URL}/#/pagesWsla/pc/zxla/pick-case-type/index"
    FILING_URL = f"{BASE_URL}/index.html#/pagesWsla/common/wsla/index"

    def __init__(self, page: Page, *, save_debug: bool = False) -> None:
        self.page = page
        self.save_debug = save_debug

    # ==================== 主入口 ====================

    def file_case(self, case_data: dict[str, Any]) -> dict[str, Any]:
        """
        执行民事一审在线立案全流程

        Args:
            case_data: 立案数据，包含:
                - court_name: 受理法院名称（如"广州市天河区人民法院"）
                - cause_of_action: 案由（如"买卖合同纠纷"）
                - case_id: 案件ID（用于后续获取材料等）

        Returns:
            立案结果
        """
        court_name: str = case_data["court_name"]
        cause_of_action: str = case_data["cause_of_action"]

        logger.info("=" * 60)
        logger.info(str(_("开始在线立案: 法院=%s, 案由=%s")), court_name, cause_of_action)
        logger.info("=" * 60)

        try:
            # 打开案件类型选择页，点击民事一审（会打开新tab）
            self._open_civil_first_instance()

            # 步骤1: 选择受理法院
            self._step1_select_court(court_name)

            # 步骤2: 阅读须知
            self._step2_read_notice()

            # 步骤3: 选择立案案由
            self._step3_select_cause(cause_of_action)

            # 步骤4: 上传诉讼材料
            self._step4_upload_materials(case_data.get("materials", {}))

            # 步骤5: 完善案件信息
            self._step5_complete_info(case_data)

            # 步骤6: 预览（不提交）
            self._step6_preview_submit()

            logger.info(str(_("立案流程执行完成")))
            return {
                "success": True,
                "message": str(_("立案流程执行完成（已到预览页，未提交）")),
                "url": self.page.url,
            }

        except Exception as e:
            logger.error("立案失败: %s", e, exc_info=True)
            if self.save_debug:
                self._save_screenshot("error_filing_failed")
            raise ValueError(str(_("立案失败: %(error)s")) % {"error": e}) from e

    # ==================== 打开民事一审 ====================

    def _open_civil_first_instance(self) -> None:
        """设置省份并从案件类型页点击民事一审"""
        logger.info(str(_("导航到民事一审立案页")))

        # 导航到案件类型选择页（/zxfw/ 主 SPA）
        self.page.goto(self.CASE_TYPE_URL, timeout=60000, wait_until="domcontentloaded")
        self.page.get_by_text("民事一审", exact=True).wait_for(
            state="visible", timeout=30000
        )

        # 设置省份为广东省（通过 localStorage，刷新后生效）
        current_province = self.page.evaluate(
            "() => localStorage.getItem('provinceId')"
        )
        if current_province != "440000":
            self.page.evaluate(
                "() => localStorage.setItem('provinceId', '440000')"
            )
            self.page.reload(wait_until="domcontentloaded")
            self.page.get_by_text("民事一审", exact=True).wait_for(
                state="visible", timeout=30000
            )

        self._random_wait(1, 2)

        # 点击"民事一审"会打开新tab
        with self.page.context.expect_page() as new_page_info:
            self.page.get_by_text("民事一审", exact=True).click()

        new_page = new_page_info.value
        new_page.wait_for_load_state("domcontentloaded")
        # 等待立案页内容渲染完成
        new_page.locator("uni-button").first.wait_for(
            state="visible", timeout=60000
        )
        self.page = new_page
        self._random_wait(2, 3)

        logger.info(str(_("已打开民事一审立案页: %s")), self.page.url)

    # ==================== 步骤1: 选择受理法院 ====================

    def _dismiss_popup(self) -> None:
        """关闭可能出现的弹窗（如综治中心提示）"""
        close_btn = self.page.locator('uni-button:has-text("关闭")')
        try:
            close_btn.wait_for(state="visible", timeout=3000)
            close_btn.click()
            self._random_wait(0.5, 1)
        except Exception:
            pass  # 弹窗未出现，忽略

    def _dismiss_popup_by_text(self, button_text: str) -> None:
        """点击弹窗中指定文本的按钮"""
        btn = self.page.locator(f'uni-button:has-text("{button_text}")')
        try:
            btn.wait_for(state="visible", timeout=5000)
            btn.click()
            self._random_wait(1, 2)
        except Exception:
            pass  # 弹窗未出现，忽略

    def _step1_select_court(self, court_name: str) -> None:
        """搜索并选择受理法院、选择申请人类型（省份已通过localStorage设置）"""
        logger.info(str(_("步骤1: 选择受理法院 - %s")), court_name)

        # 用短关键词搜索（如"天河"而非完整法院名）
        keyword = court_name.replace("人民法院", "").replace("市", "")
        # 取最后一段区/县名，如"广州天河区" -> "天河区"
        for sep in ("区", "县"):
            if sep in keyword:
                idx = keyword.index(sep)
                keyword = keyword[max(0, idx - 2) : idx + 1]
                break

        search_input = self.page.locator(".uni-input-input").first
        search_input.click()
        self._random_wait(0.3, 0.5)
        search_input.type(keyword, delay=80)
        self._random_wait(0.5, 1)

        # 点击搜索按钮
        self.page.locator("uni-button:has-text('搜索')").click()
        self._random_wait(2, 3)

        # 选中搜索结果中的法院（checklist-box radio）
        self.page.locator(
            f'.checklist-box:has-text("{court_name}")'
        ).first.click()
        self._random_wait(1, 2)

        # 关闭可能弹出的综治中心弹窗
        self._dismiss_popup()

        # 选择"为他人或公司等组织申请"
        self.page.locator(
            '.checklist-box:has-text("为他人或公司等组织申请")'
        ).click()
        self._random_wait(0.5, 1)

        # 下一步
        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(1, 2)

        logger.info(str(_("步骤1完成: 已选择法院 %s")), court_name)

    # ==================== 步骤2: 阅读须知 ====================

    def _step2_read_notice(self) -> None:
        """勾选阅读须知，处理弹窗，选择立案方式"""
        logger.info(str(_("步骤2: 阅读须知")))

        # 勾选"已阅读同意立案须知内容"
        self.page.get_by_text("已阅读同意立案须知内容").click()
        self._random_wait(0.5, 1)

        # 下一步
        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(1, 2)

        # 弹窗1: 要素式立案
        self._dismiss_popup_by_text("不选择要素式立案")
        # 弹窗2: 智能识别要素式立案
        self._dismiss_popup_by_text("不体验智能识别要素式立案服务")

        # 选择"已准备诉状"
        self.page.get_by_text("已准备诉状", exact=True).click()
        self._random_wait(1, 2)

        logger.info(str(_("步骤2完成: 须知已确认，已选择立案方式")))

    # ==================== 步骤3: 选择立案案由 ====================

    def _step3_select_cause(self, cause_of_action: str) -> None:
        """搜索并选择案由"""
        logger.info(str(_("步骤3: 选择案由 - %s")), cause_of_action)

        # 点击"请选择"打开案由选择器
        self.page.get_by_text("请选择", exact=True).first.click()
        self._random_wait(1, 2)

        # 搜索案由（标准 input 元素，fill 触发响应式搜索）
        search_input = self.page.locator(".fd-search-input input[type=text]")
        search_input.click()
        self._random_wait(0.3, 0.5)
        search_input.fill(cause_of_action)
        self._random_wait(1, 2)

        # 点击搜索结果中第一个列表项（.fd-item）
        self.page.locator(".fd-item").first.click()
        self._random_wait(0.5, 1)

        # 下一步
        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(1, 2)

        logger.info(str(_("步骤3完成: 已选择案由 %s")), cause_of_action)

    # ==================== 步骤4: 上传诉讼材料（待实现） ====================

    def _step4_upload_materials(self, materials: dict[str, list[str]]) -> None:
        """上传诉讼材料

        Args:
            materials: 材料映射，key 为材料类型索引(0-5)，value 为文件路径列表
                0: 起诉状
                1: 当事人身份证明
                2: 委托代理人委托手续和身份材料
                3: 证据目录及证据材料
                4: 送达地址确认书
                5: 其他材料（非必传）
        """
        logger.info(str(_("步骤4: 上传诉讼材料")))

        # 给上传按钮打标记
        self.page.evaluate("""() => {
            const containers = document.querySelectorAll('.fd-com-upload-grid-container');
            containers.forEach((c, i) => {
                const b = c.querySelector('.fd-btn-add');
                if (b) b.setAttribute('data-upload-index', String(i));
            });
        }""")

        for idx_str, files in materials.items():
            idx = int(idx_str)
            if not files:
                continue

            logger.info("上传材料 %d: %s", idx, [Path(f).name for f in files])
            btn = self.page.locator(f'[data-upload-index="{idx}"]')

            with self.page.expect_file_chooser() as fc_info:
                btn.click()

            fc_info.value.set_files(files)
            # 等待上传完成（等"加载中"消失）
            self.page.wait_for_timeout(3000)
            logger.info("材料 %d 上传完成", idx)

        # 等待所有文件处理完成（"加载中"提示消失）
        loading = self.page.locator("text=加载中")
        try:
            loading.wait_for(state="hidden", timeout=90000)
        except Exception:
            pass
        self._random_wait(2, 3)

        # 下一步
        self.page.locator("uni-button:has-text('下一步')").click()
        # 点击后可能再次出现加载中
        try:
            loading.wait_for(state="hidden", timeout=90000)
        except Exception:
            pass
        self._random_wait(2, 3)

        logger.info(str(_("步骤4完成: 材料已上传")))

    # ==================== 步骤5: 完善案件信息（待实现） ====================

    def _step5_complete_info(self, case_data: dict[str, Any]) -> None:
        """完善案件信息：标的金额、原告、被告"""
        logger.info(str(_("步骤5: 完善案件信息")))

        # 填标的金额（第一个输入框）
        amount = case_data.get("target_amount", "")
        if amount:
            amount_input = self.page.locator(".uni-input-input").first
            amount_input.click()
            self._random_wait(0.3, 0.5)
            amount_input.type(str(int(float(amount))), delay=50)
            self._random_wait(0.5, 1)

        # 添加原告（法人）
        self._add_legal_person(
            section_index=0,
            name=case_data.get("plaintiff_name", ""),
            address=case_data.get("plaintiff_address", ""),
            uscc=case_data.get("plaintiff_uscc", ""),
            legal_rep=case_data.get("plaintiff_legal_rep", ""),
            phone=case_data.get("plaintiff_phone", ""),
        )

        # 添加被告（法人）
        self._add_legal_person(
            section_index=1,
            name=case_data.get("defendant_name", ""),
            address=case_data.get("defendant_address", ""),
            uscc=case_data.get("defendant_uscc", ""),
            legal_rep=case_data.get("defendant_legal_rep", ""),
            phone=case_data.get("defendant_phone", ""),
        )

        # 下一步
        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(2, 3)

        logger.info(str(_("步骤5完成: 案件信息已填写")))

    def _add_legal_person(
        self,
        *,
        section_index: int,
        name: str,
        address: str,
        uscc: str,
        legal_rep: str,
        phone: str,
    ) -> None:
        """在指定区域添加法人信息（0=原告, 1=被告）"""
        add_btns = self.page.locator('.fd-sscyr-add-btn:has-text("添加法人")')
        add_btns.nth(section_index).click()
        self._random_wait(1, 2)

        # 用 JS 填写文本字段
        self.page.evaluate(
            """(data) => {
            const items = document.querySelectorAll('.uni-forms-item');
            const nativeSet = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            function setVal(el, val) {
                nativeSet.call(el, val);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }
            for (const item of items) {
                const label = item.querySelector('.uni-forms-item__label');
                if (!label) continue;
                const text = label.textContent.trim();
                const input = item.querySelector('input[type=text]');
                if (!input || !input.offsetParent || input.value) continue;

                if (text.includes('名称') && !text.includes('证件') && data.name)
                    setVal(input, data.name);
                else if (text.includes('住所地') && data.address)
                    setVal(input, data.address);
                else if (text.includes('统一社会信用代码') && data.uscc)
                    setVal(input, data.uscc);
                else if (text.includes('法定代表人') && !text.includes('证件')
                         && !text.includes('手机') && !text.includes('固定')
                         && data.legal_rep)
                    setVal(input, data.legal_rep);
                else if (text.includes('法定代表人手机号码') && data.phone)
                    setVal(input, data.phone);
            }
        }""",
            {
                "name": name,
                "address": address,
                "uscc": uscc,
                "legal_rep": legal_rep,
                "phone": phone,
            },
        )
        self._random_wait(0.5, 1)

        # 选择"证照类型" → "统一社会信用代码"
        self._select_dropdown("证照类型", "统一社会信用代码")

        # 点击"保存"
        self.page.locator("uni-button:has-text('保存')").click()
        self._random_wait(2, 3)

    def _select_dropdown(self, label_text: str, option_text: str) -> None:
        """点击包含 label_text 的下拉框，选择 option_text"""
        self.page.evaluate(
            """(data) => {
            const items = document.querySelectorAll('.uni-forms-item');
            for (const item of items) {
                const label = item.querySelector('.uni-forms-item__label');
                if (!label || !label.textContent.includes(data.label)) continue;
                const picker = item.querySelector('.uni-input-input');
                if (picker && picker.offsetParent) { picker.click(); break; }
            }
        }""",
            {"label": label_text},
        )
        self._random_wait(1, 2)
        self.page.locator(f".fd-item:has-text('{option_text}')").first.click()
        self._random_wait(0.5, 1)

    # ==================== 步骤6: 预览和提交（待实现） ====================

    def _step6_preview_submit(self) -> None:
        """预览提交页 - 仅查看，不点提交"""
        logger.info(str(_("步骤6: 预览（不提交）")))
        self._random_wait(2, 3)
        logger.info(str(_("步骤6完成: 已到达预览页，未提交")))

    # ==================== 工具方法 ====================

    def _random_wait(self, min_sec: float = 0.5, max_sec: float = 2.0) -> None:
        """随机等待，模拟人工操作"""
        time.sleep(random.uniform(min_sec, max_sec))

    def _save_screenshot(self, name: str) -> str:
        """保存调试截图"""
        from datetime import datetime

        from django.conf import settings

        screenshot_dir = Path(settings.MEDIA_ROOT) / "automation" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = screenshot_dir / filename

        self.page.screenshot(path=str(filepath))
        logger.info("截图已保存: %s", filepath)
        return str(filepath)
