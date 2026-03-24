"""金诚同达 OA 客户导入脚本。

通过 Playwright 自动化完成：
登录 → 进入客户管理页 → 遍历客户列表 → 进入详情页 → 提取字段。

复用 JtnFilingScript._login() 的登录逻辑。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Generator

from playwright.sync_api import BrowserContext, Page, sync_playwright

logger = logging.getLogger("apps.oa_filing.jtn_client_import")

# ============================================================
# 常量：URL
# ============================================================
_LOGIN_URL = "https://ims.jtn.com/member/login.aspx"
_CLIENT_LIST_URL = "https://ims.jtn.com/customer/index.aspx?Category=A&FirstModel=PROJECT&SecondModel=PROJECT001"
_BASE_URL = "https://ims.jtn.com/customer"

# 等待时间（秒）
_SHORT_WAIT = 0.5
_MEDIUM_WAIT = 1.5
_AJAX_WAIT = 2.0


@dataclass
class OACustomerData:
    """OA客户数据。"""

    name: str  # 客户名称
    client_type: str  # natural=自然人 / legal=企业
    phone: str | None = None  # 联系电话
    address: str | None = None  # 地址
    id_number: str | None = None  # 身份证号码（自然人）
    legal_representative: str | None = None  # 法定代表人（企业）
    gender: str | None = None  # 性别（自然人）


@dataclass
class CustomerListItem:
    """客户列表项。"""

    name: str
    client_type: str  # natural=自然人 / legal=企业
    key_id: str  # 客户KeyID，用于构造详情页URL


class JtnClientImportScript:
    """金诚同达 OA 客户导入自动化。"""

    def __init__(
        self,
        account: str,
        password: str,
        *,
        headless: bool = True,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._account = account
        self._password = password
        self._headless = bool(headless)
        self._progress_callback = progress_callback
        self._page: Page | None = None
        self._context: BrowserContext | None = None

    def run(self, *, limit: int | None = None) -> Generator[OACustomerData, None, None]:
        """执行客户导入流程，yield 每条客户数据。

        优化策略：先翻页收集所有客户详情URL，再批量打开详情页提取数据。
        """
        pw = sync_playwright().start()
        browser = None
        try:
            browser = pw.chromium.launch(headless=self._headless)
            self._context = browser.new_context()
            self._context.set_default_timeout(30_000)
            self._context.set_default_navigation_timeout(30_000)
            self._page = self._context.new_page()

            self._emit_progress("discovery_started", message="正在登录OA并进入客户列表")
            self._login()
            self._navigate_to_client_list()

            # 步骤1: 翻页收集所有客户的名称和详情URL
            logger.info("=== 步骤1: 翻页收集客户列表 ===")
            all_items: list[CustomerListItem] = []
            page_index = 0
            while True:
                items = self._extract_page_customers()
                page_index += 1
                all_items.extend(items)
                logger.info("本页共 %d 个客户，已累计 %d 个", len(items), len(all_items))
                self._emit_progress(
                    "discovery_progress",
                    page=page_index,
                    page_count=len(items),
                    discovered_count=len(all_items),
                    message=f"正在查找并发现当事人（第{page_index}页）",
                )

                # 点击下一页
                if limit is not None and limit > 0 and len(all_items) >= limit:
                    all_items = all_items[:limit]
                    self._emit_progress(
                        "discovery_progress",
                        page=page_index,
                        page_count=len(items),
                        discovered_count=len(all_items),
                        message=f"已达到导入上限 {limit} 条",
                    )
                    break

                if not self._click_next_page():
                    break

            logger.info("共收集到 %d 个客户", len(all_items))
            self._emit_progress(
                "discovery_completed",
                discovered_count=len(all_items),
                total_count=len(all_items),
                message=f"已发现 {len(all_items)} 条，准备开始导入",
            )

            # 步骤2: 批量打开详情页提取数据
            logger.info("=== 步骤2: 批量打开详情页 ===")
            self._emit_progress("import_started", total_count=len(all_items), message="开始导入当事人")
            for i, item in enumerate(all_items):
                logger.info("处理详情 [%d/%d]: %s", i + 1, len(all_items), item.name)
                self._emit_progress(
                    "import_progress",
                    index=i + 1,
                    total_count=len(all_items),
                    discovered_count=len(all_items),
                    name=item.name,
                    message=f"正在导入当事人 ({i + 1}/{len(all_items)})",
                )
                data = self._fetch_customer_detail(item)
                if data:
                    yield data
                time.sleep(_SHORT_WAIT)

            self._emit_progress("import_collected", total_count=len(all_items), message="当事人详情提取完成")
            logger.info("客户导入完成，共处理 %d 个客户", len(all_items))
        finally:
            if browser is not None:
                browser.close()
            pw.stop()

    def _emit_progress(self, event: str, **payload: Any) -> None:
        if self._progress_callback is None:
            return
        try:
            self._progress_callback({"event": event, **payload})
        except Exception:
            logger.debug("进度回调处理异常: event=%s", event, exc_info=True)

    def _login(self) -> None:
        """通过 httpx 接口登录，将 cookie 注入 Playwright context。"""
        import re

        import httpx

        logger.info("接口登录: %s", _LOGIN_URL)

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        with httpx.Client(headers=headers, follow_redirects=True, timeout=15) as client:
            # 1. GET 登录页，拿 ASP.NET_SessionId + CSRFToken
            r = client.get(_LOGIN_URL)
            csrf_match = re.search(r'name=["\']CSRFToken["\'] value=["\']([^"\']+)["\']', r.text)
            csrf = csrf_match.group(1) if csrf_match else ""

            # 2. POST 登录
            r2 = client.post(
                _LOGIN_URL,
                data={"CSRFToken": csrf, "userid": self._account, "password": self._password},
            )

            if "login" in str(r2.url).lower() or "logout" in r2.text.lower()[:200]:
                raise RuntimeError(f"OA 登录失败，账号或密码错误: {self._account}")

            # 3. 将 cookie 注入 Playwright context
            assert self._context is not None
            for cookie in client.cookies.jar:
                self._context.add_cookies(
                    [
                        {
                            "name": cookie.name,
                            "value": cookie.value or "",
                            "domain": cookie.domain or "ims.jtn.com",
                            "path": cookie.path or "/",
                        }
                    ]
                )

        logger.info("接口登录成功，cookie 已注入，当前重定向URL: %s", r2.url)

    def _navigate_to_client_list(self) -> None:
        """导航到客户列表页。"""
        page = self._page
        assert page is not None

        logger.info("导航到客户列表页: %s", _CLIENT_LIST_URL)
        page.goto(_CLIENT_LIST_URL, wait_until="domcontentloaded")
        time.sleep(_MEDIUM_WAIT)
        logger.info("已进入客户列表页面")

    def _extract_page_customers(self) -> list[CustomerListItem]:
        """提取当前页所有客户信息。

        Returns:
            List of CustomerListItem.
        """
        import re

        page = self._page
        assert page is not None

        customers: list[CustomerListItem] = []

        # 等待表格加载
        page.wait_for_selector("#table", timeout=15000)
        time.sleep(_AJAX_WAIT)

        # 查找表格中的客户名称单元格
        # 表格结构: table#table > tbody > tr
        # 客户名称在 td:nth-child(3)，客户类型在 td:nth-child(5)
        rows = page.locator("#table tbody tr").all()
        for row in rows:
            try:
                name_cell = row.locator("td:nth-child(3)")
                type_cell = row.locator("td:nth-child(5)")

                # 从 a 标签获取客户名称和 KeyID
                name_link = name_cell.locator("a").first
                if name_link.count() == 0:
                    continue

                name_text = name_link.inner_text().strip()
                href = name_link.get_attribute("href") or ""

                # 从 href 中提取 KeyID
                # 格式: CustomerInfor.aspx?KeyID=xxx&Category=...
                key_id = ""
                if "KeyID=" in href:
                    match = re.search(r"KeyID=([^&]+)", href)
                    if match:
                        key_id = match.group(1)

                type_text = type_cell.inner_text().strip()

                if name_text and type_text:
                    # 跳过表头行
                    if "客户类型" in type_text or "等级" in type_text or not key_id:
                        continue
                    # 判断是企业还是自然人
                    client_type = "legal" if "企业" in type_text else "natural"
                    customers.append(CustomerListItem(name=name_text, client_type=client_type, key_id=key_id))
                    logger.info("发现客户: %s (%s), KeyID: %s", name_text, client_type, key_id)
            except Exception as exc:
                logger.warning("提取客户行异常: %s", exc)
                continue

        return customers

    def _fetch_customer_detail(self, item: CustomerListItem) -> OACustomerData | None:
        """打开客户详情页，提取字段。"""
        page = self._page
        assert page is not None

        logger.info("进入客户详情: %s (KeyID: %s)", item.name, item.key_id)

        try:
            # 直接导航到详情页
            detail_url = f"{_BASE_URL}/CustomerInfor.aspx?KeyID={item.key_id}&Category=A&FirstModel=PROJECT&SecondModel=PROJECT001"
            page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(_MEDIUM_WAIT)

            # 提取详情页字段
            data = self._parse_customer_detail(item.name, item.client_type)
            return data

        except Exception as exc:
            logger.warning("提取客户详情异常 %s: %s", item.name, exc)
            # 返回基础数据
            return OACustomerData(
                name=item.name,
                client_type=item.client_type,
            )

    def _parse_customer_detail(self, customer_name: str, client_type: str) -> OACustomerData:
        """解析客户详情页，提取字段。"""
        import re

        page = self._page
        assert page is not None

        # 基础数据
        data = OACustomerData(name=customer_name, client_type=client_type)

        try:
            # 获取页面文本内容
            text = page.inner_text("body")

            # 身份证号码 - 15或18位
            m = re.search(r"身份证号码[：:]\s*([A-Z0-9]{15,18})", text)
            if m:
                data.id_number = m.group(1)

            # 性别
            m = re.search(r"性　　别[：:]\s*([男女])", text)
            if m:
                data.gender = m.group(1)

            # 联系电话（只匹配包含数字的值）
            m = re.search(r"联系电话[：:]\s*([0-9][^\t\n]*)", text)
            if m:
                val = m.group(1).strip()
                if val and val != "：" and not data.phone:
                    data.phone = val

            # 客户电话
            m = re.search(r"客户电话[：:]\s*([0-9][^\t\n]*)", text)
            if m:
                val = m.group(1).strip()
                if val and val != "：" and not data.phone:
                    data.phone = val

            # 地址（身份证地址优先）
            m = re.search(r"身份证地址[：:]\s*([^\t\n][^\t\n]*)", text)
            if m:
                val = m.group(1).strip()
                if val and val != "：" and val != "/":
                    data.address = val

            # 普通地址
            m = re.search(r"地　　址[：:]\s*([^\t\n][^\t\n]*)", text)
            if m:
                val = m.group(1).strip()
                if val and val != "：" and val != "/" and not data.address:
                    data.address = val

            # 法定代表人
            m = re.search(r"法定代表人[：:]\s*([^\t\n][^\t\n]*)", text)
            if m:
                val = m.group(1).strip()
                if val and val != "：" and val != "/":
                    data.legal_representative = val

            # 客户类型（从详情页确认）
            if "自然人" in text:
                data.client_type = "natural"
            elif "企业" in text and ("法定代表人" in text or "负责人" in text):
                data.client_type = "legal"
            elif "法定代表人" in text or "负责人" in text:
                # 有法定代表人或负责人，不是自然人，设为企业
                data.client_type = "legal"

            # 过滤无效电话（如"1"、"/"等）
            if data.phone and (data.phone in ("1", "/", "：") or len(data.phone) < 7):
                data.phone = None

        except Exception as exc:
            logger.warning("解析客户详情异常 %s: %s", customer_name, exc)

        logger.info(
            "解析客户详情完成: %s, type=%s, phone=%s, address=%s, id=%s",
            data.name,
            data.client_type,
            data.phone,
            data.address,
            data.id_number,
        )
        return data

    def _click_next_page(self) -> bool:
        """点击下一页按钮。

        Returns:
            True if successfully clicked and loaded next page, False if no more pages.
        """
        page = self._page
        assert page is not None

        try:
            # layui 分页组件的下一页按钮
            next_btn = page.locator(".layui-laypage-next")
            if next_btn.count() == 0:
                logger.info("未找到下一页按钮，已到最后一页")
                return False

            # 检查是否禁用（最后一页）
            is_disabled = next_btn.get_attribute("class")
            if "disabled" in (is_disabled or ""):
                logger.info("下一页按钮已禁用，已到最后一页")
                return False

            next_btn.click()
            time.sleep(_AJAX_WAIT)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(_SHORT_WAIT)
            logger.info("已点击下一页")
            return True

        except Exception as exc:
            logger.warning("点击下一页异常: %s", exc)
            return False
