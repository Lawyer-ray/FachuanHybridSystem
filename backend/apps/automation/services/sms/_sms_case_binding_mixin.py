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

    def _create_case_binding(self, sms: CourtSMS) -> bool:  # pragma: no cover
        """创建案件绑定和日志"""
        if not sms.case:
            logger.error("SMS %s 没有关联案件，无法创建绑定", sms.id)
            return False

        try:
            # 软解绑旧的 case_log（不删日志、不删附件），避免重新绑定时文书重复
            self._unbind_old_case_log(sms)

            from apps.core.dependencies.automation_sms_wiring import build_sms_case_log_service

            case_log_service = build_sms_case_log_service()
            logger.info("获取 case_log_service 成功: SMS ID=%s", sms.id)

            admin_lawyer_dto = self.lawyer_service.get_admin_lawyer()
            if not admin_lawyer_dto:
                logger.error("未找到管理员用户，无法创建案件日志")
                return False

            logger.info("获取管理员律师成功: %s, ID=%s", admin_lawyer_dto.real_name, admin_lawyer_dto.id)

            system_user = self.lawyer_service.get_lawyer_model(admin_lawyer_dto.id)
            logger.info("获取系统用户成功: SMS ID=%s", sms.id)

            if sms.case_numbers:
                logger.info("开始添加案号到案件: SMS ID=%s, 案号=%s", sms.id, sms.case_numbers)
                self._add_case_numbers_to_case(sms)

            logger.info("开始创建案件日志: SMS ID=%s, Case ID=%s", sms.id, sms.case.id)
            case_log = case_log_service.create_log(
                case_id=sms.case.id,
                content=f"收到法院短信：{sms.content}",
                user=system_user,
            )

            sms.case_log = case_log
            sms.save()

            logger.info("案件绑定创建成功: SMS ID=%s, CaseLog ID=%s", sms.id, case_log.id)
            return True

        except Exception as e:
            logger.exception("创建案件绑定失败: SMS ID=%s, 错误: %s", sms.id, e)
            return False

    def _unbind_old_case_log(self, sms: CourtSMS) -> None:
        """把短信与旧案件日志**软解绑**：只置空外键，日志与附件原样保留。

        审计 P05-03：旧实现会物理删除旧 CaseLog 及其全部附件文件
        （``attachment.file.delete(save=False)`` + ``old_log.delete()``）。重新绑定案件
        通常只是纠正归属，旧日志里的正文与已归档文书是案件的历史事实，删掉不可恢复。
        这里只断引用，并在日志里留一条「原 log id=…」便于追溯。
        """
        case_log_id = getattr(sms, "case_log_id", None)
        if not case_log_id:
            return

        try:
            sms.case_log = None
            sms.save(update_fields=["case_log"])
            logger.info("已解绑旧案件日志（保留日志与附件）: SMS ID=%s, 原 CaseLog ID=%s", sms.id, case_log_id)

        except Exception as e:
            logger.warning("解绑旧案件日志失败，继续流程: SMS ID=%s, 错误: %s", sms.id, e)

    def _add_case_numbers_to_case(self, sms: CourtSMS) -> None:
        """将短信中提取的案号写入案件（如果不存在）"""
        if not sms.case or not sms.case_numbers:
            return

        try:
            valid_case_numbers = self._filter_valid_case_numbers(sms.case_numbers)
            if not valid_case_numbers:
                logger.info("短信 %s 没有有效的案号需要写入", sms.id)
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
                logger.info("为案件 %s 添加了 %s 个案号: %s", sms.case.id, added_count, valid_case_numbers)

        except Exception as e:
            logger.warning("写入案号失败: SMS ID=%s, 错误: %s", sms.id, e)

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
