"""Business logic services."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from ninja.files import UploadedFile

from apps.core.exceptions import ConflictError, PermissionDenied, ValidationException
from apps.core.infrastructure import invalidate_users_access_context
from apps.organization.dtos import LawyerCreateDTO, LawyerUpdateDTO
from apps.organization.models import LawFirm, Lawyer, Team, TeamType
from apps.organization.services.organization_access_policy import OrganizationAccessPolicy

from .upload import LawyerUploadService

logger = logging.getLogger("apps.organization")


class LawyerMutationService:
    def __init__(self, access_policy: OrganizationAccessPolicy, upload_service: LawyerUploadService | None = None) -> None:
        self.access_policy = access_policy
        self.upload_service = upload_service or LawyerUploadService()

    @transaction.atomic
    def create_lawyer(self, data: LawyerCreateDTO, user: Lawyer, license_pdf: UploadedFile | None = None) -> Lawyer:
        if not self.access_policy.can_create(user):
            logger.warning(
                "用户 %s 尝试创建律师但权限不足",
                user.pk,
                extra={"user_id": user.pk, "action": "create_lawyer"},
            )
            raise PermissionDenied(message=_("无权限创建律师"), code="PERMISSION_DENIED")

        self._validate_create_data(data)

        law_firm = None
        if data.law_firm_id:
            law_firm = LawFirm.objects.filter(id=data.law_firm_id).first()
            if not law_firm:
                raise ValidationException(
                    message=_("律所不存在"), code="LAWFIRM_NOT_FOUND", errors={"law_firm_id": str(_("无效的律所 ID"))}
                )

        lawyer = Lawyer(
            username=data.username,
            real_name=data.real_name or "",
            phone=data.phone,
            license_no=data.license_no or "",
            id_card=data.id_card or "",
            law_firm=law_firm,
            is_admin=data.is_admin,
        )
        lawyer.set_password(data.password)
        self.upload_service.attach_license_pdf(lawyer, license_pdf)
        lawyer.save()

        if data.lawyer_team_ids is not None:
            self._set_lawyer_teams(lawyer, data.lawyer_team_ids, law_firm)

        if data.biz_team_ids is not None:
            self._set_biz_teams(lawyer, data.biz_team_ids, law_firm)

        logger.info(
            "律师创建成功",
            extra={"lawyer_id": lawyer.pk, "user_id": user.pk, "action": "create_lawyer"},
        )
        return lawyer

    @transaction.atomic
    def update_lawyer(
        self,
        lawyer: Lawyer,
        data: LawyerUpdateDTO,
        user: Lawyer,
        license_pdf: UploadedFile | None = None,
    ) -> Lawyer:
        if not self.access_policy.can_update_lawyer(user=user, lawyer=lawyer):
            logger.warning(
                "用户 %s 尝试更新律师 %s 但权限不足",
                user.pk,
                lawyer.pk,
                extra={"user_id": user.pk, "lawyer_id": lawyer.pk, "action": "update_lawyer"},
            )
            raise PermissionDenied(message=_("无权限更新该律师信息"), code="PERMISSION_DENIED")

        self._validate_update_data(lawyer, data)
        self._apply_field_updates(lawyer, data)
        self.upload_service.attach_license_pdf(lawyer, license_pdf)
        lawyer.save()

        if data.lawyer_team_ids is not None:
            self._set_lawyer_teams(lawyer, data.lawyer_team_ids, lawyer.law_firm)

        if data.biz_team_ids is not None:
            self._set_biz_teams(lawyer, data.biz_team_ids, lawyer.law_firm)

        logger.info(
            "律师更新成功",
            extra={"lawyer_id": lawyer.pk, "user_id": user.pk, "action": "update_lawyer"},
        )
        return lawyer

    def _apply_field_updates(self, lawyer: Lawyer, data: LawyerUpdateDTO) -> None:
        """应用字段更新"""
        field_map = {
            "real_name": data.real_name,
            "phone": data.phone,
            "license_no": data.license_no,
            "id_card": data.id_card,
            "is_admin": data.is_admin,
        }
        for field_name, value in field_map.items():
            if value is not None:
                setattr(lawyer, field_name, value)

        if data.law_firm_id is not None:
            law_firm = LawFirm.objects.filter(id=data.law_firm_id).first()
            if not law_firm:
                raise ValidationException(
                    message=_("律所不存在"), code="LAWFIRM_NOT_FOUND", errors={"law_firm_id": str(_("无效的律所 ID"))}
                )
            lawyer.law_firm = law_firm

        if data.password:
            lawyer.set_password(data.password)

    @transaction.atomic
    def delete_lawyer(self, lawyer: Lawyer, user: Lawyer) -> None:
        if not self.access_policy.can_delete_lawyer(user=user, lawyer=lawyer):
            logger.warning(
                "用户 %s 尝试删除律师 %s 但权限不足",
                user.pk,
                lawyer.pk,
                extra={"user_id": user.pk, "lawyer_id": lawyer.pk, "action": "delete_lawyer"},
            )
            raise PermissionDenied(message=_("无权限删除该律师"), code="PERMISSION_DENIED")

        if hasattr(lawyer, "created_cases") and lawyer.created_cases.exists():
            raise ConflictError(message=_("该律师创建了案件,无法删除"), code="LAWYER_HAS_CASES")

        affected_team_ids = set(lawyer.lawyer_teams.values_list("id", flat=True))
        affected_user_ids = set(
            Lawyer.objects.filter(lawyer_teams__id__in=affected_team_ids).values_list("id", flat=True).distinct()
        )
        affected_user_ids.add(lawyer.pk)

        lawyer.delete()

        invalidate_users_access_context(list(affected_user_ids), org_access=True, case_grants=False)
        logger.info(
            "律师删除成功",
            extra={"lawyer_id": lawyer.pk, "user_id": user.pk, "action": "delete_lawyer"},
        )

    def _validate_create_data(self, data: LawyerCreateDTO) -> None:
        if Lawyer.objects.filter(username=data.username).exists():
            raise ValidationException(
                message=_("用户名已存在"), code="DUPLICATE_USERNAME", errors={"username": str(_("该用户名已被使用"))}
            )

        if data.phone and Lawyer.objects.filter(phone=data.phone).exists():
            raise ValidationException(
                message=_("手机号已存在"), code="DUPLICATE_PHONE", errors={"phone": str(_("该手机号已被使用"))}
            )

    def _validate_update_data(self, lawyer: Lawyer, data: LawyerUpdateDTO) -> None:
        if data.phone and data.phone != lawyer.phone and Lawyer.objects.filter(phone=data.phone).exists():
            raise ValidationException(
                message=_("手机号已存在"), code="DUPLICATE_PHONE", errors={"phone": str(_("该手机号已被使用"))}
            )

    def _set_lawyer_teams(self, lawyer: Lawyer, team_ids: list[int], law_firm: LawFirm | None) -> None:
        teams = list(Team.objects.filter(id__in=team_ids, team_type=TeamType.LAWYER))

        if not teams:
            raise ValidationException(
                message=_("律师必须至少关联一个律师团队"),
                code="NO_LAWYER_TEAMS",
                errors={"lawyer_team_ids": str(_("至少需要一个律师团队"))},
            )

        if law_firm and any(t.law_firm_id != law_firm.pk for t in teams):
            raise ValidationException(
                message=_("团队所属律所必须与律师所属律所一致"),
                code="TEAM_LAWFIRM_MISMATCH",
                errors={"lawyer_team_ids": str(_("团队律所不匹配"))},
            )

        old_team_ids = set(lawyer.lawyer_teams.values_list("id", flat=True))
        lawyer.lawyer_teams.set(teams)

        affected_team_ids = old_team_ids | {t.id for t in teams}
        affected_user_ids = set(
            Lawyer.objects.filter(lawyer_teams__id__in=affected_team_ids).values_list("id", flat=True).distinct()
        )

        invalidate_users_access_context(list(affected_user_ids), org_access=True, case_grants=False)

    def _set_biz_teams(self, lawyer: Lawyer, team_ids: list[int], law_firm: LawFirm | None) -> None:
        teams = list(Team.objects.filter(id__in=team_ids, team_type=TeamType.BIZ))

        if law_firm and any(t.law_firm_id != law_firm.pk for t in teams):
            raise ValidationException(
                message=_("团队所属律所必须与律师所属律所一致"),
                code="TEAM_LAWFIRM_MISMATCH",
                errors={"biz_team_ids": str(_("团队律所不匹配"))},
            )

        lawyer.biz_teams.set(teams)
