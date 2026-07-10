"""详情页 Tab 数据提取（Playwright）。"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from playwright.async_api import Page

from .http_client import _BASE_URL, _DETAIL_URL_TEMPLATE, _MEDIUM_WAIT
from .models import CaseSearchItem, OACaseCustomerData, OACaseData, OACaseInfoData, OAConflictData

logger = logging.getLogger("apps.oa_filing.jtn_case_import")


class JtnDetailExtractorMixin:  # pragma: no cover
    """详情页 Tab 数据提取。"""

    # --- 由 facade 提供 ---
    _page: Page | None

    # ------------------------------------------------------------------
    # 案件详情页提取
    # ------------------------------------------------------------------
    async def _fetch_case_detail(self: Any, search_item: CaseSearchItem) -> OACaseData | None:  # pragma: no cover
        """打开案件详情页，提取3个Tab的数据。"""
        page = self._page
        assert page is not None

        detail_url = _DETAIL_URL_TEMPLATE.format(base=_BASE_URL, keyid=search_item.keyid)
        logger.info("进入案件详情: %s (keyid: %s)", search_item.case_no, search_item.keyid)

        try:
            tables = await page.locator("table").all()
            if len(tables) < 20:
                logger.info("当前不在详情页，执行 goto...")
                await page.goto(detail_url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(_MEDIUM_WAIT)
            else:
                logger.info("当前已在详情页，直接提取数据...")

            case_data = OACaseData(case_no=search_item.case_no, keyid=search_item.keyid)

            case_data.customers = await self._extract_customer_tab()
            case_data.case_info = await self._extract_case_info_tab()
            case_data.conflicts = await self._extract_conflict_tab()

            logger.info(
                "解析案件详情完成: case_no=%s, customers=%d, conflicts=%d",
                case_data.case_no,
                len(case_data.customers),
                len(case_data.conflicts),
            )
            return case_data

        except Exception as exc:
            logger.warning("提取案件详情异常 %s: %s", search_item.case_no, exc)
            return None

    async def _extract_customer_tab(self: Any) -> list[OACaseCustomerData]:  # pragma: no cover
        """提取客户信息Tab（Tab 1）。"""
        page = self._page
        assert page is not None

        customers: list[OACaseCustomerData] = []

        try:
            tables = await page.locator("table").all()
            if len(tables) > 1:
                customer_table = tables[1]
                rows = await customer_table.locator("tr").all()

                current_customer: OACaseCustomerData | None = None

                for row in rows:
                    try:
                        cells = await row.locator("td").all()
                        if not cells:
                            continue

                        row_text = await row.inner_text()
                        cell_count = len(cells)

                        if "客户" in row_text and "信息" in row_text and "（" in row_text:
                            if current_customer and current_customer.name:
                                customers.append(current_customer)
                            name_match = re.search(r"客户（([^）]+)）信息", row_text)
                            if name_match:
                                customer_name = name_match.group(1)
                                is_legal = "企业" in row_text or "公司" in customer_name
                                current_customer = OACaseCustomerData(
                                    name=customer_name,
                                    customer_type="legal" if is_legal else "natural",
                                )
                            else:
                                current_customer = None
                            continue

                        if current_customer and cell_count >= 2:
                            for i in range(0, cell_count - 1, 2):
                                label_cell = (await cells[i].inner_text()).strip()
                                value_cell = (await cells[i + 1].inner_text()).strip() if i + 1 < cell_count else ""

                                if "地址" in label_cell:
                                    current_customer.address = value_cell
                                elif any(x in label_cell for x in ("电话", "号码")):
                                    current_customer.phone = value_cell
                                elif "身份证" in label_cell:
                                    current_customer.id_number = value_cell
                                elif "行业" in label_cell:
                                    current_customer.industry = value_cell
                                elif any(x in label_cell for x in ("法定代表", "负责人", "姓名")):
                                    current_customer.legal_representative = value_cell

                    except Exception as exc:
                        logger.debug("解析客户行异常: %s", exc)
                        continue

                if current_customer and current_customer.name:
                    customers.append(current_customer)

            logger.info("提取客户信息: %d 个客户", len(customers))
            return customers

        except Exception as exc:
            logger.warning("提取客户信息Tab异常: %s", exc)

        return customers

    async def _extract_case_info_tab(self: Any) -> OACaseInfoData | None:  # pragma: no cover
        """提取案件信息Tab（Tab 2）。"""
        page = self._page
        assert page is not None

        try:
            tables = await page.locator("table").all()
            if len(tables) > 2:
                case_table = tables[2]
                rows = await case_table.locator("tr").all()

                case_info = OACaseInfoData(case_no="")

                for row in rows:
                    try:
                        cells = await row.locator("td").all()
                        if len(cells) < 2:
                            continue

                        row_text = (await row.inner_text()).strip()

                        if "案件基本信息" in row_text:
                            continue

                        for i in range(0, len(cells) - 1, 2):
                            label = (await cells[i].inner_text()).strip()
                            value = (await cells[i + 1].inner_text()).strip()

                            if not label:
                                continue

                            if "案件名称" in label:
                                case_info.case_name = value
                            elif "案件阶段" in label:
                                case_info.case_stage = value
                            elif "收案日期" in label:
                                case_info.acceptance_date = value
                            elif "案件类别" in label or "案件类型" in label:
                                case_info.case_category = value
                            elif "业务种类" in label:
                                case_info.case_type = value
                            elif "案件负责人" in label:
                                case_info.responsible_lawyer = value
                            elif "案情简介" in label:
                                case_info.description = value[:500] if value else None
                            elif "代理何方" in label:
                                case_info.client_side = value
                            elif "案件编号" in label:
                                case_info.case_no = value

                    except Exception as exc:
                        logger.debug("解析案件信息行异常: %s", exc)
                        continue

                logger.info(
                    "提取案件信息: no=%s, name=%s, stage=%s",
                    case_info.case_no,
                    case_info.case_name,
                    case_info.case_stage,
                )
                return case_info

        except Exception as exc:
            logger.warning("提取案件信息Tab异常: %s", exc)

        return None

    async def _extract_conflict_tab(self: Any) -> list[OAConflictData]:  # pragma: no cover
        """提取利益冲突信息Tab（Tab 3）。"""
        page = self._page
        assert page is not None

        conflicts: list[OAConflictData] = []

        try:
            tables = await page.locator("table").all()
            if len(tables) > 3:
                conflict_table = tables[3]
                rows = await conflict_table.locator("tr").all()

                current_name = None
                current_type = None

                for row in rows:
                    try:
                        cells = await row.locator("td").all()
                        if not cells:
                            continue

                        row_text = (await row.inner_text()).strip()

                        if "利益冲突" in row_text:
                            continue

                        for i in range(0, len(cells) - 1, 2):
                            label = (await cells[i].inner_text()).strip()
                            value = (await cells[i + 1].inner_text()).strip() if i + 1 < len(cells) else ""

                            if not label:
                                continue

                            if "中文名称" in label and value:
                                if current_name:
                                    conflicts.append(
                                        OAConflictData(
                                            name=current_name,
                                            conflict_type=current_type,
                                        )
                                    )
                                current_name = value
                                current_type = None
                            elif ("法律地位" in label and value) or (
                                "类型" in label and "客户类型" not in label and "法律地位" not in label and value
                            ):
                                current_type = value

                    except Exception as exc:
                        logger.debug("解析利益冲突行异常: %s", exc)
                        continue

                if current_name:
                    conflicts.append(
                        OAConflictData(
                            name=current_name,
                            conflict_type=current_type,
                        )
                    )

        except Exception as exc:
            logger.warning("提取利益冲突Tab异常: %s", exc)

        logger.info("提取利益冲突: %d 个", len(conflicts))
        return conflicts
