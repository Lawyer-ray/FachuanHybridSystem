"""
财产保全申请书财产线索服务

按被申请人分组列出财产线索,使用手动序号(中文数字 + 阿拉伯数字 + 带括号数字).

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9
"""

import logging
from collections import defaultdict
from typing import Any, ClassVar

from apps.documents.services.placeholders import BasePlaceholderService, PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class PreservationPropertyClueService(BasePlaceholderService):
    """财产保全申请书财产线索服务"""

    name: str = "preservation_property_clue_service"
    display_name: str = "财产保全申请书财产线索服务"
    description: str = "生成被申请人的财产线索信息,按被申请人分组,使用手动序号"
    category: str = "litigation"
    placeholder_keys: ClassVar = ["财产保全申请书财产线索"]
    placeholder_metadata: ClassVar = {
        "财产保全申请书财产线索": {
            "display_name": "财产保全申请书财产线索",
            "description": "被申请人的财产线索信息,按被申请人分组,使用手动序号",
            "example_value": "一、李四\a1.银行账户:\a(1)开户行:XXX\a(2)账号:XXX\a(3)户名:李四",
        }
    }

    # 中文数字映射
    CHINESE_NUMBERS: ClassVar = [
        "一",
        "二",
        "三",
        "四",
        "五",
        "六",
        "七",
        "八",
        "九",
        "十",
        "十一",
        "十二",
        "十三",
        "十四",
        "十五",
        "十六",
        "十七",
        "十八",
        "十九",
        "二十",
    ]

    # 线索类型显示名称
    CLUE_TYPE_DISPLAY: ClassVar = {
        "bank": "银行账户",
        "alipay": "支付宝账户",
        "wechat": "微信账户",
        "real_estate": "不动产",
        "other": "其他",
    }

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成占位符值

        Args:
            context_data: 包含 case 对象的上下文

        Returns:
            包含占位符键值对的字典
        """
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {"财产保全申请书财产线索": ""}
        return {"财产保全申请书财产线索": self.generate_property_clue_info(case_id)}

    def _get_chinese_number(self, index: int) -> Any:
        """
        获取中文数字

        Args:
            index: 索引(从0开始)

        Returns:
            str: 中文数字
        """
        if index < len(self.CHINESE_NUMBERS):
            return self.CHINESE_NUMBERS[index]
        return str(index + 1)

    def _parse_clue_content(self, clue_type: str, content: str) -> list[str]:
        """
        解析财产线索内容

        Args:
            clue_type: 线索类型
            content: 线索内容

        Returns:
            List[str]: 解析后的内容列表

        Requirements: 8.5, 8.6, 8.7
        """
        if not content:
            return []

        # 按行分割内容
        lines = [line.strip() for line in content.strip().split("\n") if line.strip()]

        result: list[Any] = []
        for line in lines:
            if ":" in line:
                # 保留原始格式
                result.append(line)
            elif ":" in line:
                # 英文冒号转中文冒号
                result.append(line.replace(":", ":"))
            else:
                result.append(line)

        return result

    def generate_property_clue_info(self, case_id: int) -> str:
        """
        生成被申请人的财产线索信息

        按被申请人分组,使用手动序号:
        - 一级:中文数字(一、二、三...)+ 被申请人名称
        - 二级:阿拉伯数字(1. 2. 3...)+ 线索类型
        - 三级:带括号数字((1)(2)(3)...)+ 具体内容

        Args:
            case_id: 案件 ID

        Returns:
            str: 格式化后的财产线索信息

        Requirements: 1.7, 3.3, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9
        """
        from apps.core.enums import LegalStatus
        from apps.documents.services.wiring import get_case_service, get_client_service

        # 获取 client 服务和 case 服务
        client_service = get_client_service()
        case_service = get_case_service()

        # 获取被申请人(被告)
        # Requirements: 1.7
        respondent_party_dtos = case_service.get_case_parties_internal(
            case_id=case_id, legal_status=LegalStatus.DEFENDANT
        )

        if not respondent_party_dtos:
            logger.warning("未找到被申请人: case_id=%s", case_id)
            return ""

        result_parts: list[Any] = []

        for respondent_index, party_dto in enumerate(respondent_party_dtos):
            client_name = party_dto.client_name or "未知"
            client_id = party_dto.client_id

            # 一级:中文数字 + 被申请人名称
            chinese_num = self._get_chinese_number(respondent_index)
            header = f"{chinese_num}、{client_name}"

            # 获取财产线索
            # Requirements: 3.3
            clue_dtos = client_service.get_property_clues_by_client_internal(client_id)

            if not clue_dtos:
                # 没有财产线索,直接输出"暂无财产线索"
                result_parts.append(f"{header}\a暂无财产线索")
                continue

            # 按线索类型分组
            clues_by_type: dict[str, list[Any]] = defaultdict(list)
            for clue in clue_dtos:
                clues_by_type[clue.clue_type].append(clue)

            # 构建该被申请人的财产线索内容
            clue_parts = [header]

            for clue_type_index, (clue_type, clue_list) in enumerate(clues_by_type.items(), 1):
                type_display = self.CLUE_TYPE_DISPLAY.get(clue_type, clue_type)

                # 二级:阿拉伯数字 + 线索类型
                type_header = f"{clue_type_index}.{type_display}:"
                clue_parts.append(type_header)

                # 三级:带括号数字 + 具体内容
                item_index = 0
                for clue in clue_list:
                    content_lines = self._parse_clue_content(clue.clue_type, clue.content)

                    if content_lines:
                        for line in content_lines:
                            item_index += 1
                            clue_parts.append(f"({item_index}){line}")

            # 使用 \a 换行符连接
            result_parts.append("\a".join(clue_parts))

        # 用 \a\a 分隔各被申请人
        result = "\a\a".join(result_parts)

        logger.info("生成财产保全申请书财产线索成功: case_id=%s, 被申请人数=%s", case_id, len(respondent_party_dtos))

        return result

    def get_respondents_without_clues(self, case_id: int) -> list[str]:
        """
        获取没有财产线索的被申请人名称列表

        Args:
            case_id: 案件 ID

        Returns:
            List[str]: 被申请人名称列表

        Requirements: 1.7, 3.3
        """
        from apps.core.enums import LegalStatus
        from apps.documents.services.wiring import get_case_service, get_client_service

        # 获取 client 服务和 case 服务
        client_service = get_client_service()
        case_service = get_case_service()

        # 获取被申请人(被告)
        # Requirements: 1.7
        respondent_party_dtos = case_service.get_case_parties_internal(
            case_id=case_id, legal_status=LegalStatus.DEFENDANT
        )

        missing_clue_respondents: list[Any] = []

        for party_dto in respondent_party_dtos:
            # 检查是否有财产线索
            clue_dtos = client_service.get_property_clues_by_client_internal(party_dto.client_id)
            if not clue_dtos:
                missing_clue_respondents.append(party_dto.client_name or "未知")

        return missing_clue_respondents
