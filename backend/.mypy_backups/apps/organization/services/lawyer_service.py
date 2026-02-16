"""
律师服务层
处理律师相关的业务逻辑
"""
from typing import List, Optional, Set
from django.db import transaction
from django.db.models import QuerySet, Q

from apps.core.exceptions import (
    ValidationException,
    PermissionDenied,
    NotFoundError,
    ConflictError
)
from apps.core.interfaces import LawyerDTO, ILawyerService
from ..models import Lawyer, Team, LawFirm, TeamType
from ..schemas import LawyerCreateIn, LawyerUpdateIn
import logging

logger = logging.getLogger("apps.organization")


class LawyerService:
    """
    律师服务

    职责：
    1. 封装律师相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    4. 协调多个 Model 操作
    """

    def __init__(self):
        """初始化服务"""
        pass

    def get_lawyer_queryset(self) -> QuerySet[Lawyer]:
        """
        获取带预加载的律师查询集

        Returns:
            律师查询集
        """
        return Lawyer.objects.select_related("law_firm").prefetch_related(
            "lawyer_teams", "biz_teams"
        )

    def get_lawyer(self, lawyer_id: int, user: Lawyer) -> Lawyer:
        """
        获取律师

        Args:
            lawyer_id: 律师 ID
            user: 当前用户

        Returns:
            律师对象

        Raises:
            NotFoundError: 律师不存在
            PermissionDenied: 无权限访问
        """
        lawyer = self.get_lawyer_queryset().filter(id=lawyer_id).first()

        if not lawyer:
            raise NotFoundError(
                message=f"律师不存在",
                code="LAWYER_NOT_FOUND"
            )

        # 权限检查
        if not self._check_read_permission(user, lawyer):
            raise PermissionDenied(
                message="无权限访问该律师信息",
                code="PERMISSION_DENIED"
            )

        return lawyer

    def list_lawyers(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: dict = None,
        user: Lawyer = None
    ) -> QuerySet[Lawyer]:
        """
        列表查询

        Args:
            page: 页码
            page_size: 每页数量
            filters: 过滤条件
            user: 当前用户

        Returns:
            律师查询集
        """
        filters = filters or {}

        # 构建基础查询
        queryset = self.get_lawyer_queryset()

        # 应用权限过滤
        if user and not user.is_superuser:
            # 普通用户只能看到同律所的律师
            queryset = queryset.filter(law_firm_id=user.law_firm_id)

        # 应用业务过滤
        if filters.get('search'):
            queryset = queryset.filter(
                Q(username__icontains=filters['search']) |
                Q(real_name__icontains=filters['search'])
            )

        if filters.get('law_firm_id'):
            queryset = queryset.filter(law_firm_id=filters['law_firm_id'])

        # 排序
        queryset = queryset.order_by('-id')

        # 分页
        start = (page - 1) * page_size
        end = start + page_size

        return queryset[start:end]

    @transaction.atomic
    def create_lawyer(
        self,
        data: LawyerCreateIn,
        user: Lawyer,
        license_pdf=None
    ) -> Lawyer:
        """
        创建律师

        Args:
            data: 创建数据
            user: 当前用户
            license_pdf: 律师执照文件

        Returns:
            创建的律师对象

        Raises:
            ValidationException: 数据验证失败
            PermissionDenied: 权限不足
        """
        # 1. 权限检查
        if not self._check_create_permission(user):
            logger.warning(
                f"用户 {user.id} 尝试创建律师但权限不足",
                extra={"user_id": user.id, "action": "create_lawyer"}
            )
            raise PermissionDenied(
                message="无权限创建律师",
                code="PERMISSION_DENIED"
            )

        # 2. 业务验证
        self._validate_create_data(data, user)

        # 3. 获取律所
        law_firm = None
        if data.law_firm_id:
            law_firm = LawFirm.objects.filter(id=data.law_firm_id).first()
            if not law_firm:
                raise ValidationException(
                    message="律所不存在",
                    code="LAWFIRM_NOT_FOUND",
                    errors={"law_firm_id": "无效的律所 ID"}
                )

        # 4. 创建律师
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

        if license_pdf is not None:
            lawyer.license_pdf.save(license_pdf.name, license_pdf, save=False)

        lawyer.save()

        # 5. 设置团队关系
        if data.lawyer_team_ids is not None:
            self._set_lawyer_teams(lawyer, data.lawyer_team_ids, law_firm)

        if data.biz_team_ids is not None:
            self._set_biz_teams(lawyer, data.biz_team_ids, law_firm)

        # 6. 记录日志
        logger.info(
            f"律师创建成功",
            extra={
                "lawyer_id": lawyer.id,
                "user_id": user.id,
                "action": "create_lawyer"
            }
        )

        return lawyer

    @transaction.atomic
    def update_lawyer(
        self,
        lawyer_id: int,
        data: LawyerUpdateIn,
        user: Lawyer,
        license_pdf=None
    ) -> Lawyer:
        """
        更新律师

        Args:
            lawyer_id: 律师 ID
            data: 更新数据
            user: 当前用户
            license_pdf: 律师执照文件

        Returns:
            更新后的律师对象

        Raises:
            NotFoundError: 律师不存在
            PermissionDenied: 权限不足
            ValidationException: 数据验证失败
        """
        # 1. 获取律师
        lawyer = self.get_lawyer(lawyer_id, user)

        # 2. 权限检查
        if not self._check_update_permission(user, lawyer):
            logger.warning(
                f"用户 {user.id} 尝试更新律师 {lawyer_id} 但权限不足",
                extra={
                    "user_id": user.id,
                    "lawyer_id": lawyer_id,
                    "action": "update_lawyer"
                }
            )
            raise PermissionDenied(
                message="无权限更新该律师信息",
                code="PERMISSION_DENIED"
            )

        # 3. 业务验证
        self._validate_update_data(lawyer, data, user)

        # 4. 更新字段
        if data.real_name is not None:
            lawyer.real_name = data.real_name
        if data.phone is not None:
            lawyer.phone = data.phone
        if data.license_no is not None:
            lawyer.license_no = data.license_no
        if data.id_card is not None:
            lawyer.id_card = data.id_card
        if data.is_admin is not None:
            lawyer.is_admin = data.is_admin

        if data.law_firm_id is not None:
            law_firm = LawFirm.objects.filter(id=data.law_firm_id).first()
            if not law_firm:
                raise ValidationException(
                    message="律所不存在",
                    code="LAWFIRM_NOT_FOUND",
                    errors={"law_firm_id": "无效的律所 ID"}
                )
            lawyer.law_firm = law_firm

        if data.password:
            lawyer.set_password(data.password)

        if license_pdf is not None:
            lawyer.license_pdf.save(license_pdf.name, license_pdf, save=False)

        lawyer.save()

        # 5. 更新团队关系
        if data.lawyer_team_ids is not None:
            self._set_lawyer_teams(lawyer, data.lawyer_team_ids, lawyer.law_firm)

        if data.biz_team_ids is not None:
            self._set_biz_teams(lawyer, data.biz_team_ids, lawyer.law_firm)

        # 6. 记录日志
        logger.info(
            f"律师更新成功",
            extra={
                "lawyer_id": lawyer.id,
                "user_id": user.id,
                "action": "update_lawyer"
            }
        )

        return lawyer

    @transaction.atomic
    def delete_lawyer(self, lawyer_id: int, user: Lawyer) -> None:
        """
        删除律师

        Args:
            lawyer_id: 律师 ID
            user: 当前用户

        Raises:
            NotFoundError: 律师不存在
            PermissionDenied: 权限不足
            ConflictError: 律师正在使用中
        """
        # 1. 获取律师
        lawyer = self.get_lawyer(lawyer_id, user)

        # 2. 权限检查
        if not self._check_delete_permission(user, lawyer):
            logger.warning(
                f"用户 {user.id} 尝试删除律师 {lawyer_id} 但权限不足",
                extra={
                    "user_id": user.id,
                    "lawyer_id": lawyer_id,
                    "action": "delete_lawyer"
                }
            )
            raise PermissionDenied(
                message="无权限删除该律师",
                code="PERMISSION_DENIED"
            )

        # 3. 业务验证（检查是否可以删除）
        # 检查是否有关联的案件、合同等
        if hasattr(lawyer, 'created_cases') and lawyer.created_cases.exists():
            raise ConflictError(
                message="该律师创建了案件，无法删除",
                code="LAWYER_HAS_CASES"
            )

        # 4. 删除律师
        lawyer.delete()

        # 5. 记录日志
        logger.info(
            f"律师删除成功",
            extra={
                "lawyer_id": lawyer_id,
                "user_id": user.id,
                "action": "delete_lawyer"
            }
        )

    def get_lawyers_by_ids(self, lawyer_ids: List[int]) -> List[Lawyer]:
        """批量获取律师"""
        return list(self.get_lawyer_queryset().filter(id__in=lawyer_ids))

    def get_team_members(self, team_id: int) -> List[Lawyer]:
        """获取团队成员"""
        try:
            team = Team.objects.prefetch_related("lawyers").get(id=team_id)
            return list(team.lawyers.all())
        except Team.DoesNotExist:
            return []

    def get_team_member_ids(self, user: Lawyer) -> Set[int]:
        """
        获取用户所在团队的所有成员 ID

        Args:
            user: 用户对象

        Returns:
            成员 ID 集合
        """
        member_ids: Set[int] = set()

        teams = user.lawyer_teams.prefetch_related("lawyers").all()
        for team in teams:
            for member in team.lawyers.all():
                member_ids.add(member.id)

        if not member_ids:
            member_ids.add(user.id)

        return member_ids

    # ========== 私有方法（业务逻辑封装） ==========

    def _check_create_permission(self, user: Lawyer) -> bool:
        """检查创建权限（私有方法）"""
        return user.is_authenticated and (user.is_superuser or user.is_admin)

    def _check_read_permission(self, user: Lawyer, lawyer: Lawyer) -> bool:
        """检查读取权限（私有方法）"""
        # 超级管理员可以访问所有律师
        if user.is_superuser:
            return True

        # 用户可以访问同律所的律师
        return user.law_firm_id == lawyer.law_firm_id

    def _check_update_permission(self, user: Lawyer, lawyer: Lawyer) -> bool:
        """检查更新权限（私有方法）"""
        # 超级管理员可以更新所有律师
        if user.is_superuser:
            return True

        # 律所管理员可以更新同律所的律师
        if user.is_admin and user.law_firm_id == lawyer.law_firm_id:
            return True

        # 用户可以更新自己的信息
        return user.id == lawyer.id

    def _check_delete_permission(self, user: Lawyer, lawyer: Lawyer) -> bool:
        """检查删除权限（私有方法）"""
        # 只有超级管理员或律所管理员可以删除律师
        return user.is_superuser or (user.is_admin and user.law_firm_id == lawyer.law_firm_id)

    def _validate_create_data(self, data: LawyerCreateIn, user: Lawyer) -> None:
        """验证创建数据（私有方法）"""
        # 检查用户名是否重复
        if Lawyer.objects.filter(username=data.username).exists():
            raise ValidationException(
                message="用户名已存在",
                code="DUPLICATE_USERNAME",
                errors={"username": "该用户名已被使用"}
            )

        # 检查手机号是否重复
        if data.phone and Lawyer.objects.filter(phone=data.phone).exists():
            raise ValidationException(
                message="手机号已存在",
                code="DUPLICATE_PHONE",
                errors={"phone": "该手机号已被使用"}
            )

    def _validate_update_data(
        self,
        lawyer: Lawyer,
        data: LawyerUpdateIn,
        user: Lawyer
    ) -> None:
        """验证更新数据（私有方法）"""
        # 检查手机号是否与其他律师重复
        if data.phone and data.phone != lawyer.phone:
            if Lawyer.objects.filter(phone=data.phone).exists():
                raise ValidationException(
                    message="手机号已存在",
                    code="DUPLICATE_PHONE",
                    errors={"phone": "该手机号已被使用"}
                )

    def _set_lawyer_teams(
        self,
        lawyer: Lawyer,
        team_ids: List[int],
        law_firm: Optional[LawFirm]
    ) -> None:
        """设置律师团队（私有方法）"""
        teams = list(Team.objects.filter(id__in=team_ids, team_type=TeamType.LAWYER))

        if not teams:
            raise ValidationException(
                message="律师必须至少关联一个律师团队",
                code="NO_LAWYER_TEAMS",
                errors={"lawyer_team_ids": "至少需要一个律师团队"}
            )

        if law_firm and any(t.law_firm_id != law_firm.id for t in teams):
            raise ValidationException(
                message="团队所属律所必须与律师所属律所一致",
                code="TEAM_LAWFIRM_MISMATCH",
                errors={"lawyer_team_ids": "团队律所不匹配"}
            )

        lawyer.lawyer_teams.set(teams)

    def _set_biz_teams(
        self,
        lawyer: Lawyer,
        team_ids: List[int],
        law_firm: Optional[LawFirm]
    ) -> None:
        """设置业务团队（私有方法）"""
        teams = list(Team.objects.filter(id__in=team_ids, team_type=TeamType.BIZ))

        if law_firm and any(t.law_firm_id != law_firm.id for t in teams):
            raise ValidationException(
                message="团队所属律所必须与律师所属律所一致",
                code="TEAM_LAWFIRM_MISMATCH",
                errors={"biz_team_ids": "团队律所不匹配"}
            )

        lawyer.biz_teams.set(teams)

    def _get_lawyer_internal(self, lawyer_id: int) -> Optional[Lawyer]:
        """
        内部方法：获取律师（无权限检查）

        供 ServiceAdapter 等内部组件调用，绕过权限检查。
        不应在 API 层直接调用此方法。

        Args:
            lawyer_id: 律师 ID

        Returns:
            律师对象，不存在时返回 None
        """
        return self.get_lawyer_queryset().filter(id=lawyer_id).first()


class LawyerServiceAdapter(ILawyerService):
    """
    律师服务适配器
    实现跨模块接口，将 Model 转换为 DTO
    """

    def __init__(self, service: Optional[LawyerService] = None):
        """初始化适配器"""
        self.service = service or LawyerService()

    def _to_dto(self, lawyer: Lawyer) -> LawyerDTO:
        """将 Model 转换为 DTO"""
        return LawyerDTO(
            id=lawyer.id,
            username=lawyer.username,
            real_name=lawyer.real_name,
            phone=lawyer.phone,
            is_admin=lawyer.is_admin,
            law_firm_id=lawyer.law_firm_id,
            law_firm_name=lawyer.law_firm.name if lawyer.law_firm else None,
        )

    def get_lawyer(self, lawyer_id: int) -> Optional[LawyerDTO]:
        """获取律师信息"""
        lawyer = self.service._get_lawyer_internal(lawyer_id)
        if not lawyer:
            return None
        return self._to_dto(lawyer)

    def get_lawyers_by_ids(self, lawyer_ids: List[int]) -> List[LawyerDTO]:
        """批量获取律师信息"""
        lawyers = self.service.get_lawyers_by_ids(lawyer_ids)
        return [self._to_dto(lawyer) for lawyer in lawyers]

    def get_team_members(self, team_id: int) -> List[LawyerDTO]:
        """获取团队成员"""
        members = self.service.get_team_members(team_id)
        return [self._to_dto(m) for m in members]

    def get_admin_lawyer_internal(self) -> Optional[LawyerDTO]:
        """
        内部方法：获取管理员律师
        
        Returns:
            管理员律师 DTO，不存在时返回 None
        """
        admin_lawyer = Lawyer.objects.filter(is_admin=True).first()
        if admin_lawyer:
            return self._to_dto(admin_lawyer)
        return None

    def get_all_lawyer_names_internal(self) -> List[str]:
        """
        内部方法：获取所有律师姓名
        
        Returns:
            所有律师的姓名列表
        """
        names = Lawyer.objects.values_list('real_name', flat=True).filter(
            real_name__isnull=False
        ).exclude(real_name='')
        return list(names)

    def get_lawyer_internal(self, lawyer_id: int) -> Optional[Lawyer]:
        """
        内部方法：获取律师 Model 对象（无权限检查）
        
        供跨模块内部调用，返回原始 Model 对象用于 ForeignKey 赋值等场景。
        
        Args:
            lawyer_id: 律师 ID
            
        Returns:
            律师 Model 对象，不存在时返回 None
        """
        return self.service._get_lawyer_internal(lawyer_id)
