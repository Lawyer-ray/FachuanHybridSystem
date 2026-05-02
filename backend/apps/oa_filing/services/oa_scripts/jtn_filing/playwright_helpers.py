"""金诚同达 OA 立案脚本 —— Playwright 表单操作工具。"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from playwright.sync_api import FrameLocator, Page

from .constants import (
    _AJAX_WAIT,
    _MEDIUM_WAIT,
    _SHORT_WAIT,
    _XPATH_CREATE_NEW_BTN,
    _XPATH_PERSONAL_TAB,
    _XPATH_SEARCH_BTN,
    _CUSTOMER_TYPE_MAP,
    _CUSTOMER_TYPE_SUB_MAP,
)
from .filing_models import ClientInfo, _gender_from_id_number

logger = logging.getLogger("apps.oa_filing.jtn")


class PlaywrightHelpersMixin:
    """Playwright 表单操作工具 mixin。"""

    _page: Page | None

    # ------------------------------------------------------------------
    # 主页面 select / input
    # ------------------------------------------------------------------

    def _set_select(self: Any, page: Page, element_id: str, value: str) -> None:
        """设置主页面 select 的值并触发 change 事件（非 Chosen.js）。"""
        page.evaluate(
            f"""(val) => {{
            var el = document.getElementById('{element_id}');
            if (el) {{
                el.value = val;
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
        }}""",
            value,
        )

    def _set_field(self: Any, page: Page, element_id: str, value: str) -> None:
        """通过 id 设置 input/textarea 的值。"""
        page.evaluate(
            f"""(val) => {{
            var el = document.getElementById('{element_id}');
            if (el) el.value = val;
        }}""",
            value,
        )

    def _set_field_by_name(self: Any, page: Page, name: str, value: str) -> None:
        """通过 name 属性设置 select/input 的值。"""
        page.evaluate(
            f"""(val) => {{
            var el = document.querySelector('[name="{name}"]');
            if (el) el.value = val;
        }}""",
            value,
        )

    @staticmethod
    def _js_str(value: str) -> str:
        """将 Python 字符串转为安全的 JS 字符串字面量。"""
        escaped: str = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
        return f"'{escaped}'"

    # ------------------------------------------------------------------
    # CreateCustomer iframe 操作
    # ------------------------------------------------------------------

    def _eval_create_iframe(self: Any, page: Page, js_code: str, *args: Any) -> Any:
        """在 CreateCustomer iframe 内执行 JS。

        js_code 是一个 JS 函数字符串，函数签名为 (arg?) => {...}。
        iframe 变量由本方法在 page.evaluate 的包装层注入。
        """
        wrapped = f"""(arg) => {{
            const iframe = document.querySelector('iframe[src*="CreateCustomer"]');
            if (!iframe) return null;
            const fn = {js_code};
            return fn(arg);
        }}"""
        arg = args[0] if args else None
        return page.evaluate(wrapped, arg)

    def _set_chosen(self: Any, page: Page, field_id: str, value: str) -> None:
        """设置 Chosen.js 下拉框的值并触发更新事件。"""
        self._eval_create_iframe(
            page,
            f"""(val) => {{
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            $('#{field_id}', doc).val(val);
            $('#{field_id}', doc).trigger('chosen:updated');
            $('#{field_id}', doc).trigger('change');
        }}""",
            value,
        )

    def _set_input(self: Any, page: Page, field_id: str, value: str) -> None:
        """通过 jQuery 设置输入框的值。"""
        self._eval_create_iframe(
            page,
            f"""(val) => {{
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            $('#{field_id}', doc).val(val);
        }}""",
            value,
        )

    # ------------------------------------------------------------------
    # 客户搜索弹窗 / iframe
    # ------------------------------------------------------------------

    def _find_latest_client_iframe(self: Any, page: Page) -> str:
        """动态查找最新的 layui-layer-iframe。

        每次打开搜索弹窗，iframe ID 会递增（100002, 100003, ...）。
        取 ID 最大的那个即为当前弹窗。
        """
        iframe_id: str = (
            page.evaluate(
                """() => {
            const iframes = document.querySelectorAll('iframe[id^="layui-layer-iframe"]');
            if (iframes.length === 0) return '';
            let maxId = '';
            let maxNum = -1;
            for (const f of iframes) {
                const num = parseInt(f.id.replace('layui-layer-iframe', ''), 10);
                if (num > maxNum) {
                    maxNum = num;
                    maxId = f.id;
                }
            }
            return maxId;
        }"""
            )
            or ""
        )
        if not iframe_id:
            logger.warning("未找到 layui-layer-iframe，回退到默认 ID")
            iframe_id = "layui-layer-iframe100002"
        logger.info("使用 iframe: %s", iframe_id)
        return f'//*[@id="{iframe_id}"]'

    def _get_latest_iframe_id(self: Any, page: Page) -> str:
        """获取当前最新弹窗 iframe 的 id。"""
        return (
            page.evaluate(
                """() => {
            const iframes = document.querySelectorAll('iframe[id^="layui-layer-iframe"]');
            let maxId = '', maxNum = -1;
            for (const f of iframes) {
                const num = parseInt(f.id.replace('layui-layer-iframe', ''), 10);
                if (num > maxNum) { maxNum = num; maxId = f.id; }
            }
            return maxId;
        }"""
            )
            or "layui-layer-iframe100002"
        )

    # ------------------------------------------------------------------
    # 客户搜索 / 选择 / 创建
    # ------------------------------------------------------------------

    def _try_select_client(self: Any, page: Page, iframe: FrameLocator) -> bool:
        """尝试在搜索结果中选中第一个客户并确认。

        layui table radio 选中需通过内部缓存 LAY_CHECKED 标志，
        然后直接调用 parent.projectAppReg.loadCustomer 并关闭弹窗。
        """
        try:
            # 检查客户名称列（第4列，index=3）是否有实际内容
            name_cells = iframe.locator('xpath=//*[@id="form1"]/div[5]/div[2]/div[2]/table/tbody/tr/td[4]/div')
            if name_cells.count() == 0:
                return False
            first_name = name_cells.first.inner_text().strip()
            if not first_name:
                return False

            # 通过 JS 设置 layui table 内部缓存的选中状态，然后调用确认逻辑
            iframe_id = self._get_latest_iframe_id(page)
            page.evaluate(
                """(iframeId) => {
                const iframe = document.getElementById(iframeId);
                if (!iframe) return;
                const layui = iframe.contentWindow.layui;
                const cache = layui.table.cache['custable'];
                if (!cache || cache.length === 0) return;
                cache[0]['LAY_CHECKED'] = true;
                const data = [cache[0]];
                data[0]['istemp'] = 'Z';
                iframe.contentWindow.parent.projectAppReg.loadCustomer(data);
                const index = iframe.contentWindow.parent.layer.getFrameIndex(iframe.contentWindow.name);
                iframe.contentWindow.parent.layer.close(index);
            }""",
                iframe_id,
            )
            time.sleep(_MEDIUM_WAIT)
            logger.info("已选中已有客户: %s", first_name)
            return True
        except Exception as exc:
            logger.info("搜索结果检查异常: %s", exc)
        return False

    def _create_new_client(
        self: Any,
        iframe: FrameLocator,
        client: ClientInfo,
    ) -> None:
        """点击创建新客户，进入二级 iframe 并填充所有必填字段。

        二级 iframe 的 id 是动态生成的（layui-layer-iframeXXXXX），
        通过 src 匹配 CreateCustomer.aspx 来定位。
        所有 Chosen.js 下拉框统一通过 jQuery 操作。
        """
        iframe.locator(f"xpath={_XPATH_CREATE_NEW_BTN}").click()
        time.sleep(_MEDIUM_WAIT)

        assert self._page is not None
        page = self._page

        type_value: str = _CUSTOMER_TYPE_MAP.get(client.client_type, "01")
        is_natural: bool = client.client_type == "natural"

        # ── 1. 选择客户类型（触发 change 事件加载客户类型细分） ──
        self._eval_create_iframe(
            page,
            """(typeValue) => {
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            $('#customer_Type', doc).val(typeValue);
            $('#customer_Type', doc).trigger('chosen:updated');
            $('#customer_Type', doc).trigger('change');
        }""",
            type_value,
        )
        time.sleep(_AJAX_WAIT)

        # ── 2. 客户类型细分 ──
        type_sub: str = _CUSTOMER_TYPE_SUB_MAP.get(client.client_type, "01-08")
        self._set_chosen(page, "customer_Type_zj", type_sub)

        # ── 3. 基本信息 ──
        self._set_input(page, "customer_name", client.name)
        self._set_input(page, "customer_Address", client.address or "/")
        self._set_input(page, "customer_callNo", client.phone or "/")

        # ── 4. 固定默认值下拉框 ──
        self._set_chosen(page, "customer_country", "01")  # 中国
        self._set_chosen(page, "customer_Source", "01")  # 主动开拓获得客户

        if is_natural:
            self._fill_natural_person(page, client)
        else:
            self._fill_enterprise(page, client)

        # ── 5. 点击确定提交（使用原生 click 确保事件冒泡到委托处理器） ──
        self._eval_create_iframe(
            page,
            """() => {
            const doc = iframe.contentDocument;
            const btn = doc.getElementById('btnSaveCustomer');
            if (btn) btn.click();
        }""",
        )
        time.sleep(_MEDIUM_WAIT)
        logger.info("已提交创建客户: %s (%s)", client.name, client.client_type)

    def _fill_enterprise(self: Any, page: Page, client: ClientInfo) -> None:
        """填充企业类型特有的必填字段。"""
        self._set_chosen(page, "customer_is_IPO", "0")  # 否
        self._set_chosen(page, "customer_is_FiveQ", "0")  # 否
        self._set_chosen(page, "customer_is_ChinaTopFiveH", "0")  # 否

        # 行业 - 随便选"批发和零售业"，触发 change 加载行业细分
        self._eval_create_iframe(
            page,
            """() => {
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            $('#customer_hangye', doc).val('06');
            $('#customer_hangye', doc).trigger('chosen:updated');
            $('#customer_hangye', doc).trigger('change');
        }""",
        )
        time.sleep(_AJAX_WAIT)

        # 行业细分 - 选第一个非空选项
        self._eval_create_iframe(
            page,
            """() => {
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            const opts = $('#customer_hangye_zj option', doc);
            if (opts.length > 1) {
                $('#customer_hangye_zj', doc).val(opts.eq(1).val());
                $('#customer_hangye_zj', doc).trigger('chosen:updated');
            }
        }""",
        )

        # 法定代表人信息
        self._set_chosen(page, "customer_Statutory", "01")  # 法定代表人
        self._set_chosen(page, "customer_Statutory_Positions", "01")  # 董事长
        self._set_input(
            page,
            "customer_Statutory_name",
            client.legal_representative or "/",
        )
        self._set_input(page, "customer_Statutory_tel", "/")

    def _fill_natural_person(self: Any, page: Page, client: ClientInfo) -> None:
        """填充自然人类型特有的必填字段。"""
        id_number: str = client.id_number or ""

        gender: str = _gender_from_id_number(id_number)
        self._set_chosen(page, "customer_PersonSex", gender)

        self._set_input(page, "customer_PersonCard", id_number)
        # 出生日期由 OA 页面的 getBirth 事件自动从身份证号提取，
        # 但需要触发 blur 事件
        self._eval_create_iframe(
            page,
            """() => {
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            $('#customer_PersonCard', doc).trigger('blur');
        }""",
        )
        time.sleep(_SHORT_WAIT)

        # 如果出生日期仍为空，手动从身份证号提取
        self._eval_create_iframe(
            page,
            f"""() => {{
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            if (!$('#customer_PersonBirth', doc).val()) {{
                const id = '{id_number}';
                if (id.length === 18) {{
                    const y = id.substring(6, 10);
                    const m = id.substring(10, 12);
                    const d = id.substring(12, 14);
                    $('#customer_PersonBirth', doc).val(y + '-' + m + '-' + d);
                }}
            }}
        }}""",
        )

        # 身份证地址 = 客户地址
        self._set_input(
            page,
            "customer_PersonAddress",
            client.address or "/",
        )
