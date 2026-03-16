"""短信案件绑定 Mixin"""

import logging
import re
from typing import TYPE_CHECKING

from apps.automation.models import CourtSMS

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseService, ILawyerService

logger = logging.getLogger("apps.automation")


class SMSCaseBindingMixin:
    """负责案件绑定、案号写入逻辑"""

    @property
    def case_service(self) -> "ICaseService":
        raise NotImplementedError

    @property
    def lawyer_service(self) -> "ILawyerService":
        raise NotImplementedError

    def _create_case_binding(self, sms: CourtSMS) -> bool:
        """创建案件绑定和日志"""
        if not sms.case:
            logger.error(f"SMS {sms.id} 没有关联案件，无法创建绑定")
            return False

        try:
            from apps.core.dependencies.automation_sms_wiring import build_sms_case_log_service

            case_log_service = build_sms_case_log_service()
            logger.info(f"获取 case_log_service 成功: SMS ID={sms.id}")

            admin_lawyer_dto = self.lawyer_service.get_admin_lawyer()
            if not admin_lawyer_dto:
                logger.error("未找到管理员用户，无法创建案件日志")
                return False

            logger.info(f"获取管理员律师成功: {admin_lawyer_dto.real_name}, ID={admin_lawyer_dto.id}")

            system_user = self.lawyer_service.get_lawyer_model(admin_lawyer_dto.id)  # type: ignore
            logger.info(f"获取系统用户成功: SMS ID={sms.id}")

            if sms.case_numbers:
                logger.info(f"开始添加案号到案件: SMS ID={sms.id}, 案号={sms.case_numbers}")
                self._add_case_numbers_to_case(sms)

            logger.info(f"开始创建案件日志: SMS ID={sms.id}, Case ID={sms.case.id}")
            case_log = case_log_service.create_log(
                case_id=sms.case.id,
                content=f"收到法院短信：{sms.content}",
                user=system_user,
            )

            sms.case_log = case_log
            sms.save()

            logger.info(f"案件绑定创建成功: SMS ID={sms.id}, CaseLog ID={case_log.id}")
            return True

        except Exception as e:
            logger.exception(f"创建案件绑定失败: SMS ID={sms.id}, 错误: {e!s}")
            return False

    def _add_case_numbers_to_case(self, sms: CourtSMS) -> None:
        """将短信中提取的案号写入案件（如果不存在）"""
        if not sms.case or not sms.case_numbers:
            return

        try:
            valid_case_numbers = self._filter_valid_case_numbers(sms.case_numbers)
            if not valid_case_numbers:
                logger.info(f"短信 {sms.id} 没有有效的案号需要写入")
                return

            admin_lawyer_dto = self.lawyer_service.get_admin_lawyer()
            user_id = admin_lawyer_dto.id if admin_lawyer_dto else None

            added_count = sum(
                1
                for num in valid_case_numbers
                if self.case_service.add_case_number_internal(
                    case_id=sms.case.id,
                    case_number=num,
                    user_id=user_id,
                )
            )

            if added_count > 0:
                logger.info(f"为案件 {sms.case.id} 添加了 {added_count} 个案号: {valid_case_numbers}")

        except Exception as e:
            logger.warning(f"写入案号失败: SMS ID={sms.id}, 错误: {e!s}")

    def _filter_valid_case_numbers(self, case_numbers: list[str]) -> list[str]:
        """过滤掉日期格式等无效案号"""
        valid = []
        for num in case_numbers:
            if "年" in num and "月" in num and "日" in num:
                continue
            if "年" in num and "月" in num and num.endswith("号") and re.match(r"^\d{4}年\d{1,2}月\d{1,2}号?$", num):
                continue
            valid.append(num)
        return valid
