"""
全国法院"一张网"在线立案服务 (zxfw.court.gov.cn)
支持民事一审和申请执行的全流程自动化
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

    民事一审流程（6步）:
    1. 选择受理法院 → 2. 阅读须知 → 3. 选择案由 → 4. 上传材料 → 5. 完善信息 → 6. 预览

    申请执行流程（5步）:
    1. 选择受理法院 → 2. 阅读须知 → 3. 上传材料(含执行依据) → 4. 完善信息 → 5. 预览
    """

    BASE_URL = "https://zxfw.court.gov.cn/zxfw"
    CASE_TYPE_URL = f"{BASE_URL}/#/pagesWsla/pc/zxla/pick-case-type/index"

    # 省份代码映射
    PROVINCE_CODES: dict[str, str] = {
        "广东省": "440000",
        "北京市": "110000",
        "上海市": "310000",
        "浙江省": "330000",
        "江苏省": "320000",
        "山东省": "370000",
        "四川省": "510000",
        "湖北省": "420000",
        "湖南省": "430000",
        "福建省": "350000",
        "河南省": "410000",
        "河北省": "130000",
        "安徽省": "340000",
        "重庆市": "500000",
        "天津市": "120000",
    }

    # 申请执行 - 当事人区域标题映射
    EXEC_SECTION_MAP: dict[str, str] = {
        "plaintiffs": "申请执行人信息",
        "defendants": "被执行人信息",
    }

    # 民事一审 - 当事人区域标题映射
    CIVIL_SECTION_MAP: dict[str, str] = {
        "plaintiffs": "原告信息",
        "defendants": "被告信息",
        "third_parties": "第三人信息",
    }

    def __init__(self, page: Page, *, save_debug: bool = False) -> None:
        self.page = page
        self.save_debug = save_debug

    # ==================== 主入口 ====================

    def file_case(self, case_data: dict[str, Any], token: str | None = None) -> dict[str, Any]:
        """执行民事一审在线立案全流程。

        优先尝试纯接口立案（需要 token），失败后回退到 Playwright。
        """
        if token:
            try:
                from apps.automation.services.scraper.sites.court_zxfw_filing_api import CourtZxfwFilingApiService

                with CourtZxfwFilingApiService(token) as api_svc:
                    result = api_svc.file_civil_case(case_data)
                logger.info("接口立案成功: %s", result)
                return result
            except Exception as api_err:
                logger.warning("接口立案失败，回退 Playwright: %s", api_err)

        court_name: str = case_data["court_name"]
        cause_of_action: str = case_data["cause_of_action"]

        logger.info("=" * 60)
        logger.info(str(_("开始民事一审立案: 法院=%s, 案由=%s")), court_name, cause_of_action)
        logger.info("=" * 60)

        try:
            province = case_data.get("province", "广东省")
            province_code = self.PROVINCE_CODES.get(province, "440000")

            self._open_case_type_page("民事一审", province_code)
            self._step1_select_court(court_name)
            self._step2_read_notice()
            self._step3_select_cause(cause_of_action)
            self._step4_upload_materials(case_data.get("materials", {}))
            self._step5_complete_info(case_data, section_map=self.CIVIL_SECTION_MAP)
            self._click_next_step()
            self._step6_preview_submit()

            logger.info(str(_("民事一审立案流程执行完成")))
            return {"success": True, "message": str(_("立案流程执行完成（已到预览页，未提交）")), "url": self.page.url}

        except Exception as e:
            logger.error("民事一审立案失败: %s", e, exc_info=True)
            if self.save_debug:
                self._save_screenshot("error_civil_filing")
            raise ValueError(str(_("立案失败: %(error)s")) % {"error": e}) from e

    def file_execution(self, case_data: dict[str, Any], token: str | None = None) -> dict[str, Any]:
        """执行申请执行在线立案全流程。

        优先尝试纯接口立案（需要 token），失败后回退到 Playwright。
        """
        if token:
            try:
                from apps.automation.services.scraper.sites.court_zxfw_filing_api import CourtZxfwFilingApiService

                with CourtZxfwFilingApiService(token) as api_svc:
                    result = api_svc.file_execution(case_data)
                logger.info("接口立案成功: %s", result)
                return result
            except Exception as api_err:
                logger.warning("接口立案失败，回退 Playwright: %s", api_err)

        court_name: str = case_data["court_name"]

        logger.info("=" * 60)
        logger.info(str(_("开始申请执行立案: 法院=%s")), court_name)
        logger.info("=" * 60)

        try:
            province = case_data.get("province", "广东省")
            province_code = self.PROVINCE_CODES.get(province, "440000")

            self._open_case_type_page("申请执行", province_code)
            self._step1_select_court(court_name)
            self._step2_read_notice(has_prepared_doc=False)
            self._step_exec_select_basis(case_data)
            self._step4_upload_materials(case_data.get("materials", {}))
            self._step5_complete_info(case_data, section_map=self.EXEC_SECTION_MAP)
            self._fill_execution_target_info(case_data)
            self._click_next_step()
            self._step6_preview_submit()

            logger.info(str(_("申请执行立案流程执行完成")))
            return {
                "success": True,
                "message": str(_("申请执行流程执行完成（已到预览页，未提交）")),
                "url": self.page.url,
            }

        except Exception as e:
            logger.error("申请执行立案失败: %s", e, exc_info=True)
            if self.save_debug:
                self._save_screenshot("error_exec_filing")
            raise ValueError(str(_("申请执行立案失败: %(error)s")) % {"error": e}) from e

    # ==================== 打开案件类型页 ====================

    def _open_case_type_page(self, case_type: str, province_code: str = "440000") -> None:
        """设置省份并从案件类型页点击指定类型（打开新tab）"""
        logger.info(str(_("导航到%s立案页")), case_type)

        self.page.goto(self.CASE_TYPE_URL, timeout=60000, wait_until="domcontentloaded")
        self.page.get_by_text(case_type, exact=True).wait_for(state="visible", timeout=30000)

        # 设置省份
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

        # 用短关键词搜索
        keyword = self._extract_court_keyword(court_name)

        search_input = self.page.locator(".uni-input-input").first
        search_input.click()
        self._random_wait(0.3, 0.5)
        # 三击全选后输入（覆盖已有内容）
        search_input.click(click_count=3)
        self._random_wait(0.2, 0.3)
        search_input.type(keyword, delay=80)
        self._random_wait(0.5, 1)

        # 点击搜索按钮
        self.page.locator("uni-button:has-text('搜索')").click()
        self._random_wait(2, 3)

        # 选中搜索结果中的法院（checklist-box radio）
        self.page.locator(f'.checklist-box:has-text("{court_name}")').first.click()
        self._random_wait(1, 2)

        # 关闭可能弹出的综治中心弹窗
        self._dismiss_popup()

        # 选择"为他人或公司等组织申请"
        self.page.locator('.checklist-box:has-text("为他人或公司等组织申请")').click()
        self._random_wait(0.5, 1)

        # 下一步
        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(1, 2)

        logger.info(str(_("步骤1完成: 已选择法院 %s")), court_name)

    # ==================== 步骤2: 阅读须知 ====================

    def _step2_read_notice(self, *, has_prepared_doc: bool = True) -> None:
        """勾选阅读须知，处理弹窗，选择立案方式

        Args:
            has_prepared_doc: 是否需要选择"已准备诉状"（民事一审需要，申请执行不需要）
        """
        logger.info(str(_("步骤2: 阅读须知")))

        self.page.get_by_text("已阅读同意立案须知内容").click()
        self._random_wait(0.5, 1)

        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(1, 2)

        # 弹窗: 要素式立案
        self._dismiss_popup_by_text("不选择要素式立案")
        self._dismiss_popup_by_text("不体验智能识别要素式立案服务")

        if has_prepared_doc:
            self.page.locator(".fd-name:has-text('已准备诉状')").click()
            self._random_wait(1, 2)

        logger.info(str(_("步骤2完成: 须知已确认")))

    # ==================== 步骤3: 选择立案案由 ====================

    def _step3_select_cause(self, cause_of_action: str) -> None:
        """搜索并选择案由"""
        logger.info(str(_("步骤3: 选择案由 - %s")), cause_of_action)

        # 点击"请选择"打开案由选择器
        self.page.get_by_text("请选择", exact=True).first.click()
        self._random_wait(1, 2)

        # 搜索案由
        search_input = self.page.locator(".fd-search-input .uni-input-input")
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

    # ==================== 步骤3(执行): 选择执行依据 ====================

    def _step_exec_select_basis(self, case_data: dict[str, Any]) -> None:
        """申请执行特有：选择执行依据类别和原审案号，保存后进入上传页"""
        logger.info(str(_("步骤(执行): 选择执行依据")))

        basis_type = case_data.get("execution_basis_type", "民商")
        original_case_number = case_data.get("original_case_number", "")

        # 选择执行依据类别
        self._select_dropdown_by_label("执行依据类别", basis_type)

        # 选择原审案号：先尝试从下拉列表匹配，找不到则手动输入
        self.page.locator(".uni-forms-item:has(.uni-forms-item__label:has-text('原审案号')) .input-value").first.click()
        self._random_wait(1, 2)

        # 检查下拉列表中是否有匹配项
        matched = self.page.locator(f".item-text:has-text('{original_case_number}')")
        if original_case_number and matched.count() > 0:
            matched.first.click()
        else:
            # 选择手动输入，再填写案号
            self.page.locator(".item-text:has-text('选择此项手动输入案号')").first.click()
            self._random_wait(1, 2)
            # 案号格式：（2024）粤0106民初12345号 → 年份=2024，案号=粤0106民初12345号
            import re

            year_match = re.search(r"[（(](\d{4})[）)]", original_case_number)
            year = year_match.group(1) if year_match else ""
            body = re.sub(r"^[（(]\d{4}[）)]\s*", "", original_case_number).rstrip("号")
            # 选年份下拉
            if year:
                self.page.locator(
                    ".uni-forms-item:has(.uni-forms-item__label:has-text('输入案号')) .input-value"
                ).first.click()
                self._random_wait(0.5, 1)
                self.page.locator(f".item-text:has-text('{year}')").first.click()
                self._random_wait(0.5, 1)
            # 填案号主体（末尾"号"字是页面固定后缀，不需要输入）
            inp = self.page.locator(
                ".uni-forms-item:has(.uni-forms-item__label:has-text('输入案号')) .uni-input-input"
            ).first
            inp.fill(body)
            self._random_wait(0.3, 0.5)
            inp.press("Enter")
            self._random_wait(0.5, 1)

        # 作出执行依据单位（选法院）
        self._select_dropdown_by_label("作出执行依据单位", case_data.get("court_name", ""))
        self._random_wait(0.5, 1)

        # 保存
        self.page.locator("uni-button:has-text('保存')").click()
        self._random_wait(1, 2)

        # 确认弹窗（按钮可能是 uni-button 或 .uni-modal__btn）
        try:
            self.page.locator(".uni-modal__btn_primary").wait_for(
                state="visible",
                timeout=5000,
            )
            self.page.locator(".uni-modal__btn_primary").click()
        except Exception:
            self._dismiss_popup_by_text("确定")
        self._random_wait(3, 5)

        logger.info(str(_("执行依据选择完成: %s, %s")), basis_type, original_case_number)

    def _select_dropdown_by_label(self, label_text: str, option_text: str) -> None:
        """通过 label 定位页面级下拉框（非表单内），选择选项"""
        self.page.locator(
            f".uni-forms-item:has(.uni-forms-item__label:has-text('{label_text}')) .input-value"
        ).first.click()
        self._random_wait(1, 2)
        self.page.locator(f".item-text:has-text('{option_text}')").first.click()
        self._random_wait(0.5, 1)

    # ==================== 步骤4: 上传诉讼材料 ====================

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

            for file_path in files:
                with self.page.expect_file_chooser() as fc_info:
                    btn.click()
                fc_info.value.set_files(file_path)
                # 等待单个文件上传完成
                self.page.wait_for_timeout(2000)

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

    def _step5_complete_info(
        self,
        case_data: dict[str, Any],
        *,
        section_map: dict[str, str] | None = None,
    ) -> None:
        """完善案件信息：当事人、代理人，以及民事一审的标的金额"""
        logger.info(str(_("步骤: 完善案件信息")))

        if section_map is None:
            section_map = self.CIVIL_SECTION_MAP

        is_execution = section_map is self.EXEC_SECTION_MAP

        # 民事一审才填标的金额
        if not is_execution:
            amount = case_data.get("target_amount", "")
            if amount:
                amount_input = self.page.locator(".uni-input-input").first
                amount_input.fill(str(int(float(amount))))
                self._random_wait(0.5, 1)

        # 添加当事人
        agent_phone = case_data.get("agent", {}).get("phone", "")

        for key, section_title in section_map.items():
            for party in case_data.get(key, []):
                if is_execution:
                    imported = self._import_original_party(
                        section_title=section_title,
                        name=party["name"],
                        address=party.get("address", ""),
                        phone=party.get("phone", ""),
                    )
                    if not imported:
                        if party.get("client_type") == "natural":
                            self._add_natural_person(section_title=section_title, **party)
                        else:
                            self._add_legal_person(section_title=section_title, agent_phone=agent_phone, **party)
                elif party.get("client_type") == "natural":
                    self._add_natural_person(section_title=section_title, **party)
                else:
                    self._add_legal_person(section_title=section_title, agent_phone=agent_phone, **party)

        # 兼容旧的单原告/单被告格式
        if "plaintiffs" not in case_data and case_data.get("plaintiff_name"):
            self._add_legal_person(
                section_title="原告信息",
                name=case_data["plaintiff_name"],
                address=case_data.get("plaintiff_address", ""),
                uscc=case_data.get("plaintiff_uscc", ""),
                legal_rep=case_data.get("plaintiff_legal_rep", ""),
                phone=case_data.get("plaintiff_phone", ""),
            )
        if "defendants" not in case_data and case_data.get("defendant_name"):
            self._add_legal_person(
                section_title="被告信息",
                name=case_data["defendant_name"],
                address=case_data.get("defendant_address", ""),
                uscc=case_data.get("defendant_uscc", ""),
                legal_rep=case_data.get("defendant_legal_rep", ""),
                phone=case_data.get("defendant_phone", ""),
            )

        # 补全代理人信息
        self._complete_agent_info(case_data)

        logger.info(str(_("完善案件信息: 当事人和代理人已填写")))

    def _complete_agent_info(self, case_data: dict[str, Any]) -> None:
        """补全所有待补全的代理人信息"""
        while True:
            pending = self.page.locator("text=待补全")
            if not pending.count():
                break
            logger.info("发现待补全的代理人信息，开始补全")

            # 点击待补全条目的编辑按钮
            box = self.page.locator(".fd-wsla-ryxx-box:has-text('待补全')").first
            box.locator(".fd-sscyr-option-pc-icon:has-text('编辑')").click()
            self._random_wait(1, 2)

            # 勾选所有被代理人 checkbox（uni-app 隐藏元素，用 JS 点击 label）
            self.page.evaluate("""() => {
                    const form = document.querySelector(
                        '.fd-wsla-ryxx-box:has(uni-button)'
                    );
                    if (!form) return;
                    form.querySelectorAll('uni-checkbox').forEach(uc => {
                        const input = uc.querySelector('.uni-checkbox-input');
                        if (input && !input.classList.contains('uni-checkbox-input-checked')) {
                            uc.click();
                        }
                    });
                }""")
            self._random_wait(0.5, 1)

            # 选择代理人类型 → 执业律师
            self._select_dropdown("代理人类型", "执业律师")

            # 选择代理类型 → 委托代理
            self._select_dropdown("代理类型", "委托代理")

            # 填现住址
            agent = case_data.get("agent", {})
            self._fill_field("现住址", agent.get("address", ""))

            # 是否法律援助 → 否；同意电子送达 → 是（点击 label 文字触发 radio）
            self.page.evaluate("""() => {
                    const form = document.querySelector('.fd-wsla-ryxx-box:has(uni-button)');
                    if (!form) return;
                    form.querySelectorAll('.uni-forms-item').forEach(item => {
                        const lbl = item.querySelector('.uni-forms-item__label');
                        if (!lbl) return;
                        const text = lbl.textContent.trim();
                        let target = null;
                        if (text === '是否法律援助') target = '否';
                        if (text === '同意电子送达') target = '是';
                        if (!target) return;
                        item.querySelectorAll('uni-label').forEach(l => {
                            if (l.textContent.trim() === target) l.click();
                        });
                    });
                }""")
            self._random_wait(0.5, 1)

            self._click_save()

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

    def _select_dropdown(self, label_text: str, option_text: str) -> None:
        """点击表单内下拉框并选择选项（.item-text 类型）"""
        form = self.page.locator(".fd-wsla-ryxx-box:has(uni-button:has-text('保存'))").first
        try:
            form.locator(
                f".uni-forms-item:has(.uni-forms-item__label:has-text('{label_text}')) .input-value"
            ).first.click(timeout=5000)
        except Exception:
            return
        self._random_wait(1, 2)
        try:
            self.page.locator(f".item-text:has-text('{option_text}')").first.click(timeout=5000)
        except Exception:
            self.page.keyboard.press("Escape")
            return
        self._random_wait(0.5, 1)

    def _select_tree_dropdown(self, label_text: str, option_text: str) -> None:
        """点击 uni-data-tree 下拉框并选择选项（.fd-item 类型）"""
        form = self.page.locator(".fd-wsla-ryxx-box:has(uni-button:has-text('保存'))").first
        form.locator(f".uni-forms-item:has(.uni-forms-item__label:has-text('{label_text}')) .input-value").first.click()
        self._random_wait(1, 2)
        self.page.locator(f".fd-item:has-text('{option_text}')").first.click()
        self._random_wait(0.5, 1)

    def _click_save(self) -> None:
        """点击当前表单的保存按钮"""
        save = self.page.locator("uni-button:has-text('保存')").first
        save.scroll_into_view_if_needed()
        self._random_wait(0.3, 0.5)
        save.click()
        self._random_wait(2, 3)

    def _import_original_party(
        self,
        *,
        section_title: str,
        name: str,
        address: str = "",
        phone: str = "",
    ) -> bool:
        """申请执行：从原审诉讼参与人中引入当事人，按名称匹配选择。返回是否成功引入"""
        logger.info(str(_("引入原审参与人: %s → %s")), name, section_title)

        section = self.page.locator(f".uni-section:has(.uni-section__content-title:has-text('{section_title}'))").first
        try:
            section.locator(
                '.fd-sscyr-add-btn:has-text("引入当事人"), .fd-sscyr-add-btn:has-text("引入原审诉讼参与人")'
            ).first.click(timeout=5000)
        except Exception:
            return False
        self._random_wait(2, 3)

        # 弹窗中按名称匹配点击 radio（uni-app radio 不可见，需 JS 点击）
        clicked = self.page.evaluate(
            """(name) => {
                const popup = document.querySelector('.uni-popup');
                if (!popup) return false;
                const labels = popup.querySelectorAll('uni-label');
                for (const label of labels) {
                    if (label.textContent.trim() === name) {
                        label.click();
                        return true;
                    }
                }
                return false;
            }""",
            name,
        )

        if not clicked:
            # 弹窗中没有匹配的人，用 JS 关闭（× 图标或取消按钮）
            self.page.evaluate("""() => {
                    const selectors = [
                        '.fd-dialog-close', '[class*="dialog"] [class*="close"]',
                        '.uni-popup .uni-icons', '.uni-popup [class*="close"]',
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) { el.click(); return; }
                    }
                    // fallback: 找包含 × 文字的元素
                    document.querySelectorAll('*').forEach(el => {
                        if (el.children.length === 0 && el.textContent.trim() === '×') el.click();
                    });
                }""")
            self._random_wait(1, 2)
            return False

        self._random_wait(0.5, 1)
        popup = self.page.locator(".uni-popup")
        popup.locator("uni-button:has-text('确定')").click()
        self._random_wait(2, 3)

        # 补填引入后可能缺失的字段
        if address:
            self._fill_field("住所地", address)
        if phone:
            self._fill_field_exact("联系电话", phone)

        self._click_save()
        return True

    def _fill_field_exact(self, label_text: str, value: str) -> None:
        """通过 label 精确匹配填写字段（避免 has-text 的模糊匹配）"""
        if not value:
            return
        # 用 JS 给精确匹配的 input 打临时标记，再用 Playwright fill
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

    def _add_legal_person(
        self,
        *,
        section_title: str,
        name: str,
        address: str = "",
        uscc: str = "",
        legal_rep: str = "",
        legal_rep_id_number: str = "",
        phone: str = "",
        agent_phone: str = "",
        **_: Any,
    ) -> None:
        """在指定区域添加法人信息"""
        section = self.page.locator(f".uni-section:has-text('{section_title}')").first
        section.locator('.fd-sscyr-add-btn:has-text("添加法人")').evaluate("el => el.click()")
        self._random_wait(1, 2)

        # 法定代表人手机号必须是11位手机号，座机号不符合，用代理律师手机号代替
        import re as _re

        mobile = phone if _re.fullmatch(r"1\d{10}", phone) else agent_phone

        self._fill_field("名称", name)
        self._fill_field("住所地", address)
        self._select_dropdown("证照类型", "统一社会信用代码证")
        self._fill_field("统一社会信用代码", uscc)
        self._fill_field("法定代表人/负责人", legal_rep)
        self._fill_field("法定代表人姓名", legal_rep)
        if legal_rep_id_number:
            self._select_dropdown("法定代表人证件类型", "居民身份证")
            self._fill_field("法定代表人证件号码", legal_rep_id_number)
        self._fill_field("法定代表人手机号码", mobile)
        self._fill_field("法定代表人联系电话", mobile)
        self._fill_field_exact("联系电话", mobile)

        self._click_save()

    def _add_natural_person(
        self,
        *,
        section_title: str,
        name: str,
        address: str = "",
        id_number: str = "",
        phone: str = "",
        gender: str = "男",
        **_: Any,
    ) -> None:
        """在指定区域添加自然人信息"""
        section = self.page.locator(f".uni-section:has-text('{section_title}')").first
        section.locator('.fd-sscyr-add-btn:has-text("添加自然人")').evaluate("el => el.click()")
        self._random_wait(1, 2)

        self._fill_field("姓名", name)
        self._select_dropdown("性别", gender)
        self._select_dropdown("证件类型", "居民身份证")
        self._fill_field("证件号码", id_number)
        self._fill_field("住所地", address)
        self._fill_field("联系电话", phone)

        self._click_save()

    # ==================== 执行标的信息 ====================

    def _fill_execution_target_info(self, case_data: dict[str, Any]) -> None:
        """申请执行特有：填写执行理由、执行请求、执行标的类型

        TODO: 执行理由和执行请求应从"强制执行申请书"中提取粘贴
        """
        logger.info(str(_("填写执行标的信息")))

        section = self.page.locator(".uni-section:has(.uni-section__content-title:has-text('执行标的信息'))").first
        section.scroll_into_view_if_needed()
        self._random_wait(0.5, 1)

        # TODO: 执行理由从强制执行申请书中提取
        reason = case_data.get("execution_reason", "")
        if reason:
            section.locator(".uni-forms-item:has(.uni-forms-item__label:has-text('执行理由')) textarea").fill(reason)
            self._random_wait(0.3, 0.5)

        # TODO: 执行请求从强制执行申请书中提取
        request = case_data.get("execution_request", "")
        if request:
            section.locator(".uni-forms-item:has(.uni-forms-item__label:has-text('执行请求')) textarea").fill(request)
            self._random_wait(0.3, 0.5)

        # 执行标的类型：永远勾选"金钱给付"
        label = section.locator(".checklist-text:has-text('金钱给付')")
        if label.count():
            label.first.click()
            self._random_wait(0.3, 0.5)

        logger.info(str(_("执行标的信息填写完成")))

    def _click_next_step(self) -> None:
        """点击下一步按钮"""
        self.page.locator("uni-button:has-text('下一步')").click()
        self._random_wait(2, 3)

    # ==================== 步骤6: 预览和提交（待实现） ====================

    def _step6_preview_submit(self) -> None:
        """预览提交页 - 仅查看，不点提交"""
        logger.info(str(_("步骤6: 预览（不提交）")))
        self._random_wait(2, 3)
        logger.info(str(_("步骤6完成: 已到达预览页，未提交")))

    # ==================== 工具方法 ====================

    @staticmethod
    def _extract_court_keyword(court_name: str) -> str:
        """从法院全名提取搜索关键词

        Examples:
            广州市天河区人民法院 → 天河区
            广州市中级人民法院 → 广州市中级
            深圳市南山区人民法院 → 南山区
            广州市花都区人民法院 → 花都区
            博罗县人民法院 → 博罗县
        """
        name = court_name.replace("人民法院", "")
        # 有区/县的基层法院
        for sep in ("区", "县"):
            if sep in name:
                idx = name.index(sep)
                return name[max(0, idx - 2) : idx + 1]
        # 中级/高级/铁路等特殊法院，保留去掉"人民法院"后的全名
        return name

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
