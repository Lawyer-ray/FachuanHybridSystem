from ninja import Schema, ModelSchema
from typing import Optional, List
from .models import Case, CaseParty, CaseAssignment, CaseLog, CaseLogAttachment, CaseNumber, SupervisingAuthority
from apps.client.schemas import ClientOut
from .models import CaseStage
from .models import CaseAccessGrant
from apps.core.schemas import SchemaMixin
from apps.core.interfaces import LawyerDTO, ServiceLocator


class LawyerOutFromDTO(Schema):
    """基于 LawyerDTO 的律师输出 Schema"""
    id: int
    username: str
    real_name: Optional[str] = None
    phone: Optional[str] = None

    @classmethod
    def from_dto(cls, dto: LawyerDTO) -> "LawyerOutFromDTO":
        """从 LawyerDTO 转换为 Schema"""
        return cls(
            id=dto.id,
            username=dto.username,
            real_name=dto.real_name,
            phone=dto.phone
        )


class CaseIn(ModelSchema):
    class Meta:
        model = Case
        fields = [
            "name",
            "status",
            "is_archived",
            "case_type",
            "target_amount",
            "cause_of_action",
            "current_stage",
            "effective_date",
        ]


class CaseOut(ModelSchema):
    parties: List["CasePartyOut"]
    assignments: List["CaseAssignmentOut"]
    logs: List["CaseLogOut"]
    case_numbers: List["CaseNumberOut"]
    supervising_authorities: List["SupervisingAuthorityOut"]
    contract_id: int | None
    class Meta:
        model = Case
        fields = [
            "id",
            "name",
            "status",
            "is_archived",
            "case_type",
            "start_date",
            "effective_date",
            "target_amount",
            "cause_of_action",
            "current_stage",
        ]

    @staticmethod
    def resolve_parties(obj: Case):
        return list(obj.parties.all())

    @staticmethod
    def resolve_assignments(obj: Case):
        return list(obj.assignments.all())

    @staticmethod
    def resolve_logs(obj: Case):
        return list(obj.logs.all())

    @staticmethod
    def resolve_status(obj: Case) -> str | None:
        """返回中文状态"""
        return obj.get_status_display() if obj.status else None

    @staticmethod
    def resolve_current_stage(obj: Case) -> str | None:
        return obj.get_current_stage_display() if obj.current_stage else None

    @staticmethod
    def resolve_contract_id(obj: Case) -> int | None:
        return obj.contract_id

    @staticmethod
    def resolve_case_numbers(obj: Case) -> List["CaseNumberOut"]:
        return list(obj.case_numbers.all())

    @staticmethod
    def resolve_supervising_authorities(obj: Case) -> List["SupervisingAuthorityOut"]:
        return list(obj.supervising_authorities.all())


class SupervisingAuthorityIn(Schema):
    name: Optional[str] = None
    authority_type: Optional[str] = None


class SupervisingAuthorityOut(ModelSchema, SchemaMixin):
    authority_type_display: str | None
    class Meta:
        model = SupervisingAuthority
        fields = ["id", "name", "authority_type", "created_at"]

    @staticmethod
    def resolve_authority_type_display(obj: SupervisingAuthority) -> str | None:
        return obj.get_authority_type_display() if obj.authority_type else None

    @staticmethod
    def resolve_created_at(obj: SupervisingAuthority):
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))


class SupervisingAuthorityUpdate(Schema):
    name: Optional[str] = None
    authority_type: Optional[str] = None


class CaseUpdate(Schema):
    name: Optional[str] = None
    status: Optional[str] = None
    is_archived: Optional[bool] = None
    case_type: Optional[str] = None
    target_amount: Optional[float] = None
    cause_of_action: Optional[str] = None
    current_stage: Optional[str] = None
    effective_date: Optional[str] = None


class CasePartyIn(Schema):
    case_id: int
    client_id: int
    legal_status: Optional[str] = None


class CasePartyUpdate(Schema):
    case_id: Optional[int] = None
    client_id: Optional[int] = None
    legal_status: Optional[str] = None


class CasePartyOut(ModelSchema):
    client_detail: ClientOut
    class Meta:
        model = CaseParty
        fields = ["id", "case", "client", "legal_status"]

    @staticmethod
    def resolve_client_detail(obj: CaseParty) -> ClientOut:
        return obj.client

    @staticmethod
    def resolve_legal_status(obj: CaseParty) -> str | None:
        return obj.get_legal_status_display() if obj.legal_status else None


class CaseAssignmentIn(Schema):
    case_id: int
    lawyer_id: int


class CaseAssignmentUpdate(Schema):
    case_id: Optional[int] = None
    lawyer_id: Optional[int] = None


class CaseAssignmentOut(ModelSchema):
    lawyer_detail: LawyerOutFromDTO
    class Meta:
        model = CaseAssignment
        fields = ["id", "case", "lawyer"]

    @staticmethod
    def resolve_lawyer_detail(obj: CaseAssignment) -> LawyerOutFromDTO:
        # 通过 ILawyerService 获取律师信息
        lawyer_service = ServiceLocator.get_lawyer_service()
        lawyer_dto = lawyer_service.get_lawyer(obj.lawyer_id)
        if lawyer_dto:
            return LawyerOutFromDTO.from_dto(lawyer_dto)
        # 如果通过服务获取失败，使用基本信息
        return LawyerOutFromDTO(
            id=obj.lawyer_id,
            username=f"lawyer_{obj.lawyer_id}",
            real_name=None,
            phone=None
        )


class CaseLogIn(Schema):
    case_id: int
    content: str
    reminder_type: Optional[str] = None
    reminder_time: Optional[str] = None


class CaseLogUpdate(Schema):
    case_id: Optional[int] = None
    content: Optional[str] = None
    reminder_type: Optional[str] = None
    reminder_time: Optional[str] = None


class CaseLogAttachmentOut(ModelSchema, SchemaMixin):
    file_path: str | None
    media_url: str | None
    class Meta:
        model = CaseLogAttachment
        fields = ["id", "log", "uploaded_at"]

    @staticmethod
    def resolve_file_path(obj: CaseLogAttachment) -> str | None:
        return SchemaMixin._get_file_path(obj.file)

    @staticmethod
    def resolve_media_url(obj: CaseLogAttachment) -> str | None:
        return SchemaMixin._get_file_url(obj.file)

    @staticmethod
    def resolve_uploaded_at(obj: CaseLogAttachment):
        return SchemaMixin._resolve_datetime(getattr(obj, "uploaded_at", None))


class CaseLogActorOut(Schema):
    """案件日志操作者信息"""
    id: int
    username: str
    real_name: Optional[str] = None
    phone: Optional[str] = None

    @classmethod
    def from_dto(cls, dto: LawyerDTO) -> "CaseLogActorOut":
        """从 LawyerDTO 转换为 Schema"""
        return cls(
            id=dto.id,
            username=dto.username,
            real_name=dto.real_name,
            phone=dto.phone
        )


class CaseLogOut(ModelSchema, SchemaMixin):
    attachments: List[CaseLogAttachmentOut]
    actor_detail: CaseLogActorOut
    class Meta:
        model = CaseLog
        fields = [
            "id",
            "case",
            "content",
            "reminder_type",
            "reminder_time",
            "actor",
            "created_at",
            "updated_at",
        ]

    @staticmethod
    def resolve_attachments(obj: CaseLog) -> List[CaseLogAttachmentOut]:
        return list(obj.attachments.all())

    @staticmethod
    def resolve_actor(obj: CaseLog) -> int:
        return obj.actor_id

    @staticmethod
    def resolve_actor_detail(obj: CaseLog) -> CaseLogActorOut:
        # 通过 ILawyerService 获取律师信息
        lawyer_service = ServiceLocator.get_lawyer_service()
        lawyer_dto = lawyer_service.get_lawyer(obj.actor_id)
        if lawyer_dto:
            return CaseLogActorOut.from_dto(lawyer_dto)
        # 如果通过服务获取失败，使用基本信息
        return CaseLogActorOut(
            id=obj.actor_id,
            username=f"lawyer_{obj.actor_id}",
            real_name=None,
            phone=None
        )

    @staticmethod
    def resolve_created_at(obj: CaseLog):
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj: CaseLog):
        return SchemaMixin._resolve_datetime(getattr(obj, "updated_at", None))

    @staticmethod
    def resolve_reminder_time(obj: CaseLog):
        return SchemaMixin._resolve_datetime(getattr(obj, "reminder_time", None))


class CaseLogAttachmentIn(Schema):
    log_id: int


class CaseLogAttachmentUpdate(Schema):
    log_id: Optional[int] = None


class CaseLogVersionOut(Schema):
    id: int
    content: str
    version_at: str
    actor_id: int


class CasePartyCreate(Schema):
    client_id: int
    legal_status: Optional[str] = None


class CaseAssignmentCreate(Schema):
    lawyer_id: int


class CaseLogAttachmentCreate(Schema):
    pass


class CaseLogCreate(Schema):
    content: str
    reminder_type: Optional[str] = None
    reminder_time: Optional[str] = None


class CaseNumberIn(Schema):
    case_id: int
    number: str
    remarks: Optional[str] = None


class CaseNumberOut(ModelSchema, SchemaMixin):
    class Meta:
        model = CaseNumber
        fields = [
            "id",
            "number",
            "remarks",
            "created_at",
        ]

    @staticmethod
    def resolve_created_at(obj: CaseNumber) -> str | None:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "created_at", None))


class CaseNumberUpdate(Schema):
    number: Optional[str] = None
    remarks: Optional[str] = None


class CaseCreateFull(Schema):
    case: CaseIn
    parties: Optional[list[CasePartyCreate]] = None
    assignments: Optional[list[CaseAssignmentCreate]] = None
    logs: Optional[list[CaseLogCreate]] = None
    case_numbers: Optional[list[CaseNumberIn]] = None
    supervising_authorities: Optional[list[SupervisingAuthorityIn]] = None


class CaseFullOut(Schema):
    case: CaseOut
    parties: list[CasePartyOut]
    assignments: list[CaseAssignmentOut]
    logs: list[CaseLogOut]
    case_numbers: list[CaseNumberOut]
    supervising_authorities: list[SupervisingAuthorityOut]


class CaseAccessGrantIn(Schema):
    case_id: int
    grantee_id: int


class CaseAccessGrantOut(ModelSchema, SchemaMixin):
    class Meta:
        model = CaseAccessGrant
        fields = ["id", "case", "grantee", "created_at"]

    @staticmethod
    def resolve_created_at(obj: CaseAccessGrant):
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))


class CaseAccessGrantUpdate(Schema):
    case_id: Optional[int] = None
    grantee_id: Optional[int] = None



