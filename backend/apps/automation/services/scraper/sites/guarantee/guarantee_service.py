"""一张网申请担保流程（到 gFive 预览页，不提交）。"""

from __future__ import annotations

import logging
from typing import Any

from playwright.sync_api import Page

from .base_mixin import GuaranteeBaseMixin
from .data_mixin import GuaranteeDataMixin
from .dialog_mixin import GuaranteeDialogMixin
from .form_filling_mixin import GuaranteeFormFillingMixin
from .upload_mixin import GuaranteeUploadMixin

logger = logging.getLogger("apps.automation")


class CourtZxfwGuaranteeService(
    GuaranteeDataMixin,
    GuaranteeBaseMixin,
    GuaranteeFormFillingMixin,
    GuaranteeDialogMixin,
    GuaranteeUploadMixin,
):
    """一张网申请担保流程（到 gFive 预览页，不提交）。"""

    GUARANTEE_URL = "https://zxfw.court.gov.cn/yzwbqww/index.html#/CreateGuarantee/applyGuaranteeInformation/gOne"
    MAX_SLOW_WAIT_MS = 180000
    DEFAULT_POLL_MS = 1200
    DEFAULT_NATURAL_ID_NUMBER = "110101" + "19900307" + "7715"
    DEFAULT_LEGAL_ID_NUMBER = "91440101MA59TEST8X"

    def __init__(self, page: Page, *, save_debug: bool = False) -> None:
        self.page = page
        self.save_debug = save_debug
        self._api_error_log: list[dict[str, Any]] = []

        def _on_response(response: Any) -> None:
            url = response.url
            if "baoquan" not in url and "ssbq" not in url:
                return
            if response.status >= 400:
                try:
                    body = response.text()[:2000]
                except Exception:
                    body = "<无法读取>"
                self._api_error_log.append({"url": url, "status": response.status, "body": body})
                logger.info(f"gTwo API error: {url} status={response.status} body={body[:500]}")

        page.on("response", _on_response)

    def apply_guarantee(self, case_data: dict[str, Any]) -> dict[str, Any]:
        self.page.goto(self.GUARANTEE_URL, timeout=60000, wait_until="domcontentloaded")
        self._random_wait(4, 6)
        raw_paths = case_data.get("material_paths") or []
        self._material_items: list[dict[str, str]] = []
        for item in raw_paths:
            if isinstance(item, dict):
                p = str(item.get("path") or "")
                if p:
                    self._material_items.append({"path": p, "type_name": str(item.get("type_name") or "")})
            else:
                p = str(item)
                if p:
                    self._material_items.append({"path": p, "type_name": ""})

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
            "api_error_log": self._api_error_log[-10:] if self._api_error_log else [],
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
                if any("请上传证据材料" in err or "证据" in err for err in errors):
                    self._retry_evidence_material_upload_in_g_three()
                    self._random_wait(1.4, 2.0)

            self._click_first_enabled_button(["下一步", "保存并下一步", "暂存"])
            self._random_wait(1.2, 1.8)

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
