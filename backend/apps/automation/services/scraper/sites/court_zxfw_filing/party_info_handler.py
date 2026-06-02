"""步骤 5：当事人/代理人信息填写。"""

from __future__ import annotations

import logging
import re
from typing import Any

from playwright.sync_api import Page

from .form_utils import FormUtilsMixin

logger = logging.getLogger("apps.automation")


class PartyInfoHandlerMixin(FormUtilsMixin):
    """当事人信息填写 Mixin，需要子类提供 self.page。"""

    page: Page
    CIVIL_SECTION_MAP: dict[str, str]
    EXEC_SECTION_MAP: dict[str, str]

    def _step5_complete_info(
        self,
        case_data: dict[str, Any],
        *,
        section_map: dict[str, str] | None = None,
    ) -> None:
        """完善案件信息：当事人、代理人，以及民事一审的标的金额"""
        logger.info("步骤: 完善案件信息")

        # 等待页面主体表单区域加载，确认已进入步骤5
        try:
            self.page.locator(".uni-section").first.wait_for(state="visible", timeout=15000)
        except Exception:
            raise ValueError("完善信息页面未加载，请检查前面步骤（材料上传等）是否已完成")

        # 清除一张网自动识别的当事人（避免与后续手动添加的冲突）
        self._clear_auto_recognized_parties()

        if section_map is None:
            section_map = self.CIVIL_SECTION_MAP

        is_execution = section_map is self.EXEC_SECTION_MAP

        if not is_execution:
            amount = case_data.get("target_amount", "")
            if amount:
                try:
                    amount_input = self.page.locator(
                        ".uni-forms-item:has(.uni-forms-item__label:has-text('标的金额')) .uni-input-input"
                    ).first
                    amount_input.wait_for(state="visible", timeout=10000)
                    amount_input.fill(str(int(float(amount))))
                    self._random_wait(0.5, 1)
                except Exception as e:
                    logger.warning("填写标的金额失败（可能页面未加载到该表单）: %s", e)

        agents = [item for item in case_data.get("agents", []) if isinstance(item, dict)]
        primary_agent = agents[0] if agents else case_data.get("agent", {})
        agent_phone = str(primary_agent.get("phone", "") or "")

        for key, section_title in section_map.items():
            for party in case_data.get(key, []):
                party_phone = str(party.get("phone", "") or "")
                if not self._is_mobile_phone(party_phone):
                    party_phone = agent_phone
                party_address = str(party.get("address", "") or "")

                # 归一化当事人类别
                client_type = self._normalize_client_type(party.get("client_type", ""))

                if is_execution:
                    imported = self._import_original_party(
                        section_title=section_title,
                        name=party["name"],
                        address=party_address,
                        phone=party_phone,
                    )
                    if not imported:
                        self._add_party_by_type(
                            client_type=client_type,
                            section_title=section_title,
                            agent_phone=agent_phone,
                            party=party,
                            party_phone=party_phone,
                        )
                else:
                    self._add_party_by_type(
                        client_type=client_type,
                        section_title=section_title,
                        agent_phone=agent_phone,
                        party=party,
                        party_phone=party_phone,
                    )

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

        self._complete_agent_info(case_data)

        logger.info("完善案件信息: 当事人和代理人已填写")

    def _clear_auto_recognized_parties(self) -> None:
        """清除一张网自动识别的当事人信息。

        一张网会从上传的材料中自动识别当事人，但识别结果经常不准确
        （法人/自然人混淆、信息缺失等），需要先清除再手动添加。
        """
        logger.info("检查并清除自动识别的当事人")

        cleared = 0
        for _ in range(20):
            # 查找所有"删除"按钮
            delete_btns = self.page.locator('span:has-text("删除")')
            if not delete_btns.count():
                break

            # 点击第一个删除按钮
            try:
                delete_btns.first.click()
            except Exception:
                break
            self._random_wait(0.5, 1)

            # 等待确认弹窗并点击确定
            try:
                confirm_btn = self.page.locator(".uni-modal__btn_primary")
                confirm_btn.wait_for(state="visible", timeout=3000)
                confirm_btn.click()
                self._random_wait(1, 2)
            except Exception:
                try:
                    self.page.locator('uni-button:has-text("确定")').first.click()
                    self._random_wait(1, 2)
                except Exception:
                    try:
                        self.page.locator('uni-button:has-text("取消")').first.click()
                    except Exception:
                        pass
                    break

            cleared += 1
            logger.debug("已删除第 %d 个自动识别的当事人", cleared)

        if cleared > 0:
            logger.info("已清除 %d 个自动识别的当事人", cleared)

    def _complete_agent_info(self, case_data: dict[str, Any]) -> None:
        """按案件绑定顺序补齐代理人（不足则新增）。"""
        agents = [item for item in case_data.get("agents", []) if isinstance(item, dict)]
        if not agents and isinstance(case_data.get("agent"), dict):
            agent_dict = case_data.get("agent")
            if agent_dict is not None:
                agents = [agent_dict]
        if not agents:
            return

        for index, agent in enumerate(agents):
            opened, form = self._open_agent_form(index=index)
            if not opened:
                logger.warning("代理人表单无法打开: index=%s", index)
                break
            self._fill_agent_form(case_data=case_data, agent=agent, form=form)
            self._click_save(form=form)

    def _open_agent_form(self, *, index: int) -> tuple[bool, Any]:
        section = self.page.locator(".uni-section:has(.uni-section__content-title:has-text('代理人信息'))").first
        edit_cards = section.locator(".fd-wsla-ryxx-box:has(.fd-sscyr-option-pc-icon:has-text('编辑'))")
        if edit_cards.count() > index:
            edit_cards.nth(index).locator(".fd-sscyr-option-pc-icon:has-text('编辑')").first.click()
            self._random_wait(1, 2)
            form = section.locator(".fd-wsla-ryxx-box:has(uni-button:has-text('保存'))").first
            return True, form

        create_buttons = (
            '.fd-sscyr-add-btn:has-text("添加律师"), '
            '.fd-sscyr-add-btn:has-text("添加法律服务工作者"), '
            '.fd-sscyr-add-btn:has-text("添加其他")'
        )
        add_btn = section.locator(create_buttons).first
        if not add_btn.count():
            return False, None
        add_btn.scroll_into_view_if_needed()
        add_btn.click(timeout=5000)
        self._random_wait(1, 2)
        form = section.locator(".fd-wsla-ryxx-box:has(uni-button:has-text('保存'))").first
        return bool(form.count() > 0), form

    def _fill_agent_form(self, *, case_data: dict[str, Any], agent: dict[str, Any], form: Any = None) -> None:
        if form is not None:
            form.evaluate(
                """el => {
                    el.querySelectorAll('uni-checkbox').forEach(uc => {
                        const input = uc.querySelector('.uni-checkbox-input');
                        if (input && !input.classList.contains('uni-checkbox-input-checked')) {
                            uc.click();
                        }
                    });
                }"""
            )
        else:
            self.page.evaluate(
                """() => {
                    const form = document.querySelector('.fd-wsla-ryxx-box:has(uni-button)');
                    if (!form) return;
                    form.querySelectorAll('uni-checkbox').forEach(uc => {
                        const input = uc.querySelector('.uni-checkbox-input');
                        if (input && !input.classList.contains('uni-checkbox-input-checked')) {
                            uc.click();
                        }
                    });
                }"""
            )
        self._random_wait(0.5, 1)

        plaintiffs = [item for item in case_data.get("plaintiffs", []) if isinstance(item, dict)]
        principal_name = str((plaintiffs[0].get("name") if plaintiffs else "") or "")
        if principal_name:
            if not self._select_dropdown("被代理人", principal_name, form=form):
                self._select_tree_dropdown("被代理人", principal_name, form=form)

        self._select_dropdown("代理人类型", "执业律师", form=form)
        self._select_dropdown("代理类型", "委托代理", form=form)

        phone = str(agent.get("phone", "") or "")
        address = str(agent.get("address", "") or "")
        self._fill_field("姓名", str(agent.get("name", "") or ""), form=form)
        self._fill_field("代理人姓名", str(agent.get("name", "") or ""), form=form)
        self._fill_field("证件号码", str(agent.get("id_number", "") or ""), form=form)
        self._fill_field("代理人证件号码", str(agent.get("id_number", "") or ""), form=form)
        self._fill_field("执业证号", str(agent.get("bar_number", "") or ""), form=form)
        self._fill_field("执业机构", str(agent.get("law_firm", "") or ""), form=form)
        self._fill_field("手机号码", phone, form=form)
        self._fill_field("联系电话", phone, form=form)
        self._fill_field_exact("联系电话", phone, form=form)
        self._fill_field("现住址", address, form=form)
        self._fill_field("住所地", address, form=form)

        if form is not None:
            form.evaluate(
                """el => {
                    el.querySelectorAll('.uni-forms-item').forEach(item => {
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
                }"""
            )
        else:
            self.page.evaluate(
                """() => {
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
                }"""
            )
        self._random_wait(0.5, 1)

    def _import_original_party(
        self,
        *,
        section_title: str,
        name: str,
        address: str = "",
        phone: str = "",
    ) -> bool:
        """申请执行：从原审诉讼参与人中引入当事人"""
        logger.info("引入原审参与人: %s → %s", name, section_title)

        section = self.page.locator(f".uni-section:has(.uni-section__content-title:has-text('{section_title}'))").first
        try:
            section.locator(
                '.fd-sscyr-add-btn:has-text("引入当事人"), .fd-sscyr-add-btn:has-text("引入原审诉讼参与人")'
            ).first.click(timeout=5000)
        except Exception:
            return False
        self._random_wait(2, 3)

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
            self.page.evaluate(
                """() => {
                    const selectors = [
                        '.fd-dialog-close', '[class*="dialog"] [class*="close"]',
                        '.uni-popup .uni-icons', '.uni-popup [class*="close"]',
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) { el.click(); return; }
                    }
                    document.querySelectorAll('*').forEach(el => {
                        if (el.children.length === 0 && el.textContent.trim() === '×') el.click();
                    });
                }"""
            )
            self._random_wait(1, 2)
            return False

        self._random_wait(0.5, 1)
        popup = self.page.locator(".uni-popup")
        popup.locator("uni-button:has-text('确定')").click()
        self._random_wait(2, 3)

        # 定位引入后打开的表单
        form = section.locator(".fd-wsla-ryxx-box:has(uni-button:has-text('保存'))").first

        if address:
            self._fill_field("住所地", address, form=form)
            self._fill_field("现住址", address, form=form)
            self._fill_field_exact("现住址", address, form=form)
        if phone:
            self._fill_field("联系电话", phone, form=form)
            self._fill_field_exact("联系电话", phone, form=form)
            self._fill_field("手机号码", phone, form=form)

        self._click_save(form=form)
        return True

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
        add_btn = section.locator('.fd-sscyr-add-btn:has-text("添加法人")')
        try:
            add_btn.wait_for(state="visible", timeout=10000)
        except Exception:
            raise ValueError(f"未找到「{section_title}」的添加法人按钮，请检查材料是否已完整上传")
        add_btn.evaluate("el => el.click()")
        self._random_wait(1, 2)

        # 定位新打开的表单（section 内第一个含保存按钮的表单）
        form = section.locator(".fd-wsla-ryxx-box:has(uni-button:has-text('保存'))").first

        mobile = phone if re.fullmatch(r"1\d{10}", phone) else agent_phone

        self._fill_field("名称", name, form=form)
        self._fill_field("住所地", address, form=form)
        self._select_dropdown("证照类型", "统一社会信用代码证", form=form)
        self._fill_field("统一社会信用代码", uscc, form=form)
        self._fill_field("法定代表人/负责人", legal_rep, form=form)
        self._fill_field("法定代表人姓名", legal_rep, form=form)
        if legal_rep_id_number:
            self._select_dropdown("法定代表人证件类型", "居民身份证", form=form)
            self._fill_field("法定代表人证件号码", legal_rep_id_number, form=form)
        self._fill_field("法定代表人手机号码", mobile, form=form)
        self._fill_field("法定代表人联系电话", mobile, form=form)
        self._fill_field_exact("联系电话", mobile, form=form)

        self._click_save(form=form)

    def _add_natural_person(
        self,
        *,
        section_title: str,
        name: str,
        address: str = "",
        id_number: str = "",
        phone: str = "",
        gender: str = "男",
        nationality: str = "",
        ethnicity: str = "",
        **_: Any,
    ) -> None:
        """在指定区域添加自然人信息"""
        section = self.page.locator(f".uni-section:has-text('{section_title}')").first
        add_btn = section.locator('.fd-sscyr-add-btn:has-text("添加自然人")')
        try:
            add_btn.wait_for(state="visible", timeout=10000)
        except Exception:
            raise ValueError(f"未找到「{section_title}」的添加自然人按钮，请检查材料是否已完整上传")
        add_btn.evaluate("el => el.click()")
        self._random_wait(1, 2)

        # 定位新打开的表单（section 内第一个含保存按钮的表单）
        form = section.locator(".fd-wsla-ryxx-box:has(uni-button:has-text('保存'))").first

        # 从身份证号自动推导性别（第17位奇数=男，偶数=女）
        if not gender and id_number and len(id_number) == 18:
            try:
                gender = "男" if int(id_number[16]) % 2 == 1 else "女"
            except (ValueError, IndexError):
                pass

        self._fill_field("姓名", name, form=form)
        self._fill_field("住所地", address, form=form)
        self._select_dropdown("性别", gender or "男", form=form)
        self._select_dropdown("国别或地区", nationality or "中国", form=form)
        self._select_dropdown("证件类型", "居民身份证", form=form)
        self._select_dropdown("民族", ethnicity or "汉族", form=form)
        self._fill_field("证件号码", id_number, form=form)
        self._fill_field("联系电话", phone, form=form)

        self._click_save(form=form)

    def _add_other_organization(
        self,
        *,
        section_title: str,
        name: str,
        address: str = "",
        uscc: str = "",
        legal_rep: str = "",
        phone: str = "",
        agent_phone: str = "",
        **_: Any,
    ) -> None:
        """在指定区域添加其他组织（非法人组织、个体工商户等）信息。

        与法人类似，但字段标签不同：用"主要负责人"代替"法定代表人/负责人"。
        """
        section = self.page.locator(f".uni-section:has-text('{section_title}')").first
        add_btn = section.locator('.fd-sscyr-add-btn:has-text("添加其他组织")')
        try:
            add_btn.wait_for(state="visible", timeout=10000)
        except Exception:
            # 回退：部分页面可能没有"添加其他组织"按钮，尝试"添加法人"
            logger.warning("未找到「添加其他组织」按钮，尝试「添加法人」")
            self._add_legal_person(
                section_title=section_title,
                name=name,
                address=address,
                uscc=uscc,
                legal_rep=legal_rep,
                phone=phone,
                agent_phone=agent_phone,
            )
            return
        add_btn.evaluate("el => el.click()")
        self._random_wait(1, 2)

        form = section.locator(".fd-wsla-ryxx-box:has(uni-button:has-text('保存'))").first

        mobile = phone if re.fullmatch(r"1\d{10}", phone) else agent_phone

        self._fill_field("名称", name, form=form)
        self._fill_field("住所地", address, form=form)
        self._select_dropdown("证照类型", "统一社会信用代码证", form=form)
        self._fill_field("统一社会信用代码", uscc, form=form)
        self._fill_field("主要负责人", legal_rep, form=form)
        self._fill_field("主要负责人姓名", legal_rep, form=form)
        self._fill_field("主要负责人手机号码", mobile, form=form)
        self._fill_field("主要负责人联系电话", mobile, form=form)
        self._fill_field_exact("联系电话", mobile, form=form)

        self._click_save(form=form)

    @staticmethod
    def _normalize_client_type(client_type: str) -> str:
        """归一化当事人类别：非法人组织/个体工商户/个人独资企业 → other_organization"""
        other_types = {"非法人组织", "个体工商户", "个人独资企业", "other_organization"}
        if client_type in other_types:
            return "other_organization"
        if client_type == "natural":
            return "natural"
        return "legal"

    def _add_party_by_type(
        self,
        *,
        client_type: str,
        section_title: str,
        agent_phone: str,
        party: dict[str, Any],
        party_phone: str,
    ) -> None:
        """根据当事人类别分派到对应的添加方法"""
        if client_type == "natural":
            self._add_natural_person(section_title=section_title, **{**party, "phone": party_phone})
        elif client_type == "other_organization":
            self._add_other_organization(
                section_title=section_title,
                agent_phone=agent_phone,
                **{**party, "phone": party_phone},
            )
        else:
            self._add_legal_person(
                section_title=section_title,
                agent_phone=agent_phone,
                **{**party, "phone": party_phone},
            )

    def _fill_execution_target_info(self, case_data: dict[str, Any]) -> None:
        """申请执行特有：填写执行理由、执行请求、执行标的类型"""
        logger.info("填写执行标的信息")

        section = self.page.locator(".uni-section:has(.uni-section__content-title:has-text('执行标的信息'))").first
        section.scroll_into_view_if_needed()
        self._random_wait(0.5, 1)

        reason = case_data.get("execution_reason", "")
        if reason:
            section.locator(".uni-forms-item:has(.uni-forms-item__label:has-text('执行理由')) textarea").fill(reason)
            self._random_wait(0.3, 0.5)

        request = case_data.get("execution_request", "")
        if request:
            section.locator(".uni-forms-item:has(.uni-forms-item__label:has-text('执行请求')) textarea").fill(request)
            self._random_wait(0.3, 0.5)

        label = section.locator(".checklist-text:has-text('金钱给付')")
        if label.count():
            label.first.click()
            self._random_wait(0.3, 0.5)

        logger.info("执行标的信息填写完成")

    @staticmethod
    def _is_mobile_phone(value: str) -> bool:
        return bool(re.fullmatch(r"1\d{10}", str(value or "").strip()))
