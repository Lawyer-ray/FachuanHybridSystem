"""步骤 5：当事人/代理人信息填写。"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.utils.translation import gettext_lazy as _
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
        logger.info(str(_("步骤: 完善案件信息")))

        if section_map is None:
            section_map = self.CIVIL_SECTION_MAP

        is_execution = section_map is self.EXEC_SECTION_MAP

        if not is_execution:
            amount = case_data.get("target_amount", "")
            if amount:
                amount_input = self.page.locator(".uni-input-input").first
                amount_input.fill(str(int(float(amount))))
                self._random_wait(0.5, 1)

        agents = [item for item in case_data.get("agents", []) if isinstance(item, dict)]
        primary_agent = agents[0] if agents else case_data.get("agent", {})
        agent_phone = str(primary_agent.get("phone", "") or "")

        for key, section_title in section_map.items():
            for party in case_data.get(key, []):
                party_phone = str(party.get("phone", "") or "")
                if not self._is_mobile_phone(party_phone):
                    party_phone = agent_phone
                party_address = str(party.get("address", "") or "")
                if is_execution:
                    imported = self._import_original_party(
                        section_title=section_title,
                        name=party["name"],
                        address=party_address,
                        phone=party_phone,
                    )
                    if not imported:
                        if party.get("client_type") == "natural":
                            self._add_natural_person(section_title=section_title, **{**party, "phone": party_phone})
                        else:
                            self._add_legal_person(
                                section_title=section_title,
                                agent_phone=agent_phone,
                                **{**party, "phone": party_phone},
                            )
                elif party.get("client_type") == "natural":
                    self._add_natural_person(section_title=section_title, **{**party, "phone": party_phone})
                else:
                    self._add_legal_person(
                        section_title=section_title,
                        agent_phone=agent_phone,
                        **{**party, "phone": party_phone},
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

        logger.info(str(_("完善案件信息: 当事人和代理人已填写")))

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
            if not self._open_agent_form(index=index):
                logger.warning("代理人表单无法打开: index=%s", index)
                break
            self._fill_agent_form(case_data=case_data, agent=agent)
            self._click_save()

    def _open_agent_form(self, *, index: int) -> bool:
        section = self.page.locator(".uni-section:has(.uni-section__content-title:has-text('代理人信息'))").first
        edit_cards = section.locator(".fd-wsla-ryxx-box:has(.fd-sscyr-option-pc-icon:has-text('编辑'))")
        if edit_cards.count() > index:
            edit_cards.nth(index).locator(".fd-sscyr-option-pc-icon:has-text('编辑')").first.click()
            self._random_wait(1, 2)
            return True

        create_buttons = (
            '.fd-sscyr-add-btn:has-text("添加律师"), '
            '.fd-sscyr-add-btn:has-text("添加法律服务工作者"), '
            '.fd-sscyr-add-btn:has-text("添加其他")'
        )
        add_btn = section.locator(create_buttons).first
        if not add_btn.count():
            return False
        add_btn.scroll_into_view_if_needed()
        add_btn.click(timeout=5000)
        self._random_wait(1, 2)
        return bool(self.page.locator(".fd-wsla-ryxx-box:has(uni-button:has-text('保存'))").count() > 0)

    def _fill_agent_form(self, *, case_data: dict[str, Any], agent: dict[str, Any]) -> None:
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
            if not self._select_dropdown("被代理人", principal_name):
                self._select_tree_dropdown("被代理人", principal_name)

        self._select_dropdown("代理人类型", "执业律师")
        self._select_dropdown("代理类型", "委托代理")

        phone = str(agent.get("phone", "") or "")
        address = str(agent.get("address", "") or "")
        self._fill_field("姓名", str(agent.get("name", "") or ""))
        self._fill_field("代理人姓名", str(agent.get("name", "") or ""))
        self._fill_field("证件号码", str(agent.get("id_number", "") or ""))
        self._fill_field("代理人证件号码", str(agent.get("id_number", "") or ""))
        self._fill_field("执业证号", str(agent.get("bar_number", "") or ""))
        self._fill_field("执业机构", str(agent.get("law_firm", "") or ""))
        self._fill_field("手机号码", phone)
        self._fill_field("联系电话", phone)
        self._fill_field_exact("联系电话", phone)
        self._fill_field("现住址", address)
        self._fill_field("住所地", address)

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
        logger.info(str(_("引入原审参与人: %s → %s")), name, section_title)

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

        if address:
            self._fill_field("住所地", address)
            self._fill_field("现住址", address)
            self._fill_field_exact("现住址", address)
        if phone:
            self._fill_field("联系电话", phone)
            self._fill_field_exact("联系电话", phone)
            self._fill_field("手机号码", phone)

        self._click_save()
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
        section.locator('.fd-sscyr-add-btn:has-text("添加法人")').evaluate("el => el.click()")
        self._random_wait(1, 2)

        mobile = phone if re.fullmatch(r"1\d{10}", phone) else agent_phone

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

    def _fill_execution_target_info(self, case_data: dict[str, Any]) -> None:
        """申请执行特有：填写执行理由、执行请求、执行标的类型"""
        logger.info(str(_("填写执行标的信息")))

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

        logger.info(str(_("执行标的信息填写完成")))

    @staticmethod
    def _is_mobile_phone(value: str) -> bool:
        return bool(re.fullmatch(r"1\d{10}", str(value or "").strip()))
