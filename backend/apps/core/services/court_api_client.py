"""
法院 API 客户端

负责从法院系统获取案由和法院数据.
使用 httpx 异步客户端进行 HTTP 请求.
"""

from django.utils.translation import gettext_lazy as _
import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar, cast

import httpx

from apps.core.exceptions import ValidationException

logger = logging.getLogger(__name__)


@dataclass
class CauseItem:
    """案由数据项"""

    code: str
    name: str
    case_type: str
    level: int = 1
    parent_code: str | None = None
    children: list["CauseItem"] = field(default_factory=list)


@dataclass
class CourtItem:
    """法院数据项"""

    code: str
    name: str
    level: int = 1
    province: str = ""
    parent_code: str | None = None
    children: list["CourtItem"] = field(default_factory=list)


class CourtApiClient:
    """法院 API 客户端

    负责从法院一张网 API 获取案由和法院数据.

    Attributes:
        CAUSE_API_URL: 案由数据 API 地址(一张网)
        COURT_API_URL: 法院数据 API 地址
        LBS_TYPE_MAP: lbs 参数到案件类型的映射
        DEFAULT_TIMEOUT: 默认请求超时时间(秒)
        MAX_RETRIES: 最大重试次数
    """

    # 一张网案由接口
    CAUSE_API_URL = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-lafw/api/v1/ay/tree/batch"
    COURT_API_URL = "https://baoquan.court.gov.cn/wsbq/ssbq/api/bqsqs/yzwxzfy"

    # lbs 参数到案件类型的映射
    LBS_TYPE_MAP: ClassVar = {
        "0200": "criminal",  # 刑事案由
        "0300": "civil",  # 民事案由
        "0400": "administrative",  # 行政案由
    }

    # 需要跳过的根节点名称(这些是包装层,不是真正的案由)
    ROOT_WRAPPER_NAMES: ClassVar = {
        "civil": ["民事案由"],
        "criminal": ["刑事案由或罪名"],
        "administrative": ["行政行为"],  # 行政案由也需要跳过包装层
    }

    # 需要完全排除的节点名称(包括其所有子节点)
    EXCLUDED_NAMES: ClassVar = {
        "administrative": ["行政管理类型"],  # 行政管理类型及其子节点全部排除
    }

    DEFAULT_TIMEOUT = 30.0
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0

    def __init__(self, timeout: float | None = None) -> None:
        """初始化客户端

        Args:
            timeout: 请求超时时间(秒),默认使用 DEFAULT_TIMEOUT
        """
        self.timeout = timeout or self.DEFAULT_TIMEOUT

    async def fetch_causes_by_type(self, token: str, lbs: str) -> dict[str, Any]:
        """获取指定类型的案由数据

        从法院一张网 API 获取案由数据.

        Args:
            token: JWT 认证令牌(HS256 格式)
            lbs: 案由类型参数(0200=刑事, 0300=民事, 0400=行政)

        Returns:
            API 响应数据

        Raises:
            ValidationException: 请求失败或响应无效时抛出
        """
        case_type = self.LBS_TYPE_MAP.get(lbs, lbs)
        headers = {
            "Authorization": token,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Referer": "https://zxfw.court.gov.cn/zxfw/index.html",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
            ),
        }
        params = {"lbs": lbs}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.MAX_RETRIES):
                try:
                    response = await client.get(
                        self.CAUSE_API_URL,
                        headers=headers,
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()

                    if not self._is_valid_response(data):
                        raise ValidationException(
                            message=f"{case_type}案由 API 响应格式无效",
                            errors={"response": str(data)[:500]},
                        )

                    logger.info(f"成功获取{case_type}案由数据")
                    return cast(dict[str, Any], data)

                except httpx.TimeoutException:
                    logger.warning(f"{case_type}案由 API 请求超时,第 {attempt + 1} 次重试")
                    if attempt == self.MAX_RETRIES - 1:
                        raise ValidationException(
                            message=f"{case_type}案由 API 请求超时",
                            errors={"url": self.CAUSE_API_URL, "lbs": lbs},
                        ) from None
                    import asyncio

                    await asyncio.sleep(self.RETRY_DELAY)

                except httpx.HTTPStatusError as e:
                    response_text = ""
                    try:
                        response_text = e.response.text
                    except (AttributeError, UnicodeDecodeError):
                        response_text = "<无法读取响应体>"

                    logger.error(f"{case_type}案由 API 请求失败: HTTP {e.response.status_code}")
                    raise ValidationException(
                        message=f"{case_type}案由 API 请求失败: HTTP {e.response.status_code}",
                        errors={
                            "url": str(e.request.url),
                            "status_code": e.response.status_code,
                            "response_body": response_text[:500],
                        },
                    ) from None

                except httpx.RequestError as e:
                    logger.error(f"{case_type}案由 API 请求错误: {e}")
                    raise ValidationException(
                        message=f"{case_type}案由 API 请求错误: {e}",
                        errors={"url": self.CAUSE_API_URL, "lbs": lbs},
                    ) from e

        raise ValidationException(message=f"{case_type}案由 API 请求失败")

    async def fetch_all_causes(self, token: str) -> list[CauseItem]:
        """获取所有类型的案由数据

        依次请求刑事、民事、行政案由接口,合并结果.

        Args:
            token: JWT 认证令牌(HS256 格式)

        Returns:
            所有案由数据列表

        Raises:
            ValidationException: 请求失败或响应无效时抛出
        """
        all_causes: list[CauseItem] = []

        for lbs, case_type in self.LBS_TYPE_MAP.items():
            logger.info(f"获取{case_type}案由 (lbs={lbs})...")
            response = await self.fetch_causes_by_type(token, lbs)
            causes = self.parse_cause_response(response, lbs, case_type)
            all_causes.extend(causes)
            logger.info(f"{case_type}案由获取完成,共 {len(causes)} 条顶级记录")

        logger.info(f"所有案由获取完成,共 {len(all_causes)} 条顶级记录")
        return all_causes

    async def fetch_courts(self, token: str) -> dict[str, Any]:
        """获取法院数据

        从法院系统 API 获取法院数据.

        Args:
            token: Bearer 认证令牌

        Returns:
            API 响应数据

        Raises:
            ValidationException: 请求失败或响应无效时抛出
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        params = {"mklx": "2"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.MAX_RETRIES):
                try:
                    response = await client.get(
                        self.COURT_API_URL,
                        headers=headers,
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()

                    if not self._is_valid_response(data):
                        raise ValidationException(
                            message=_("法院 API 响应格式无效"),
                            errors={"response": data},
                        )

                    logger.info("成功获取法院数据")
                    return cast(dict[str, Any], data)

                except httpx.TimeoutException:
                    logger.warning(f"法院 API 请求超时,第 {attempt + 1} 次重试")
                    if attempt == self.MAX_RETRIES - 1:
                        raise ValidationException(
                            message=_("法院 API 请求超时"),
                            errors={"url": self.COURT_API_URL},
                        ) from None
                    import asyncio

                    await asyncio.sleep(self.RETRY_DELAY)

                except httpx.HTTPStatusError as e:
                    logger.error(f"法院 API 请求失败: {e.response.status_code}")
                    raise ValidationException(
                        message=f"法院 API 请求失败: HTTP {e.response.status_code}",
                        errors={
                            "url": self.COURT_API_URL,
                            "status_code": e.response.status_code,
                        },
                    ) from e

                except httpx.RequestError as e:
                    logger.error(f"法院 API 请求错误: {e}")
                    raise ValidationException(
                        message=f"法院 API 请求错误: {e}",
                        errors={"url": self.COURT_API_URL},
                    ) from e

        raise ValidationException(message=_("法院 API 请求失败"))

    def _is_valid_response(self, data: dict[str, Any]) -> bool:
        """验证 API 响应是否有效"""
        if not isinstance(data, dict):
            return False
        code = data.get("code")
        return code == 200 or code == "200"

    def parse_cause_response(self, response_data: dict[str, Any], lbs: str, case_type: str) -> list[CauseItem]:
        """解析案由响应数据

        响应格式:{"code": 200, "data": {"code": 200, "data": {"lbs": [...]}}}

        不同案件类型的 JSON 结构:
        - 民事:根节点是"民事案由",需要跳过,取其 children(如"人格权纠纷")作为第一级
        - 刑事:根节点是"刑事案由或罪名",需要跳过,取其 children(如"危害国家安全罪")作为第一级
        - 行政:根节点是"行政行为",需要跳过;"行政管理类型"及其子节点完全排除

        Args:
            response_data: API 响应数据
            lbs: lbs 参数值
            case_type: 案件类型

        Returns:
            解析后的案由数据列表
        """
        try:
            # 嵌套结构:data.data[lbs]
            inner_data = response_data.get("data", {})
            if isinstance(inner_data, dict):
                inner_data = inner_data.get("data", {})

            data_list = inner_data.get(lbs, []) if isinstance(inner_data, dict) else []

            if not data_list:
                logger.warning(f"案由响应中未找到 data.data.{lbs} 字段")
                return []

            # 获取需要跳过的根节点名称
            wrapper_names = self.ROOT_WRAPPER_NAMES.get(case_type, [])
            # 获取需要完全排除的节点名称
            excluded_names = self.EXCLUDED_NAMES.get(case_type, [])

            # 处理包装层:如果根节点是包装层,则取其 children
            actual_data_list = []
            for item in data_list:
                item_name = item.get("name", "")

                # 完全排除的节点(包括其子节点)
                if item_name in excluded_names:
                    logger.info(f"排除节点 '{item_name}' 及其所有子节点")
                    continue

                if item_name in wrapper_names:
                    # 这是包装层,取其 children 作为实际数据
                    children = item.get("children") or []
                    # 过滤掉需要排除的子节点
                    filtered_children = [c for c in children if c.get("name", "") not in excluded_names]
                    excluded_count = len(children) - len(filtered_children)
                    if excluded_count > 0:
                        logger.info(f"从 '{item_name}' 的子节点中排除了 {excluded_count} 个节点")
                    actual_data_list.extend(filtered_children)
                    logger.info(f"跳过包装层 '{item_name}',取其 {len(filtered_children)} 个子节点")
                else:
                    # 不是包装层,直接使用
                    actual_data_list.append(item)

            if not actual_data_list:
                logger.warning(f"{case_type}案由解析后数据为空")
                return []

            result = self._parse_cause_items(actual_data_list, case_type, level=1)
            return result

        except (KeyError, TypeError) as e:
            logger.error(f"解析{case_type}案由响应失败: {e}")
            raise ValidationException(
                message=f"解析{case_type}案由响应失败: {e}",
                errors={"response": str(response_data)[:500]},
            ) from e

    def _parse_cause_items(
        self,
        items: list[dict[str, Any]],
        case_type: str,
        level: int = 1,
        parent_code: str | None = None,
    ) -> list[CauseItem]:
        """递归解析案由数据项"""
        result: list[CauseItem] = []

        for item in items:
            code = str(item.get("id", ""))
            name = item.get("name", "")

            if not code or not name:
                continue

            # children 可能是 None
            children_data = item.get("children") or []
            children = self._parse_cause_items(children_data, case_type, level=level + 1, parent_code=code)

            cause_item = CauseItem(
                code=code,
                name=name,
                case_type=case_type,
                level=level,
                parent_code=parent_code,
                children=children,
            )
            result.append(cause_item)

        return result

    def parse_court_response(self, response_data: dict[str, Any]) -> list[CourtItem]:
        """解析法院响应数据"""
        try:
            court_list = response_data.get("data", [])
            if not court_list:
                logger.warning("法院响应中未找到 data 字段")
                return []

            result = self._parse_court_items(court_list, level=1)
            logger.info(f"解析法院数据完成,共 {len(result)} 条顶级记录")
            return result

        except (KeyError, TypeError) as e:
            logger.error(f"解析法院响应失败: {e}")
            raise ValidationException(
                message=f"解析法院响应失败: {e}",
                errors={"response": response_data},
            ) from e

    def _parse_court_items(
        self,
        items: list[dict[str, Any]],
        level: int = 1,
        parent_code: str | None = None,
        province: str = "",
    ) -> list[CourtItem]:
        """递归解析法院数据项"""
        result: list[CourtItem] = []

        for item in items:
            code = str(item.get("cGbm", "") or item.get("id", ""))
            name = item.get("name", "")

            if not code or not name:
                continue

            current_province = province
            if level == 1:
                current_province = name

            children_data = item.get("children") or []
            children = self._parse_court_items(
                children_data, level=level + 1, parent_code=code, province=current_province
            )

            court_item = CourtItem(
                code=code,
                name=name,
                level=level,
                province=current_province,
                parent_code=parent_code,
                children=children,
            )
            result.append(court_item)

        return result
