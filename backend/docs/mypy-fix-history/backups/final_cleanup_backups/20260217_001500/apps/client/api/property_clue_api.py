"""
财产线索 API 层
只负责请求/响应处理，不包含业务逻辑
"""
from typing import List
from ninja import Router, File
from ninja.files import UploadedFile
from django.conf import settings
import os

from ..schemas import (
    PropertyClueIn,
    PropertyClueUpdateIn,
    PropertyClueOut,
    PropertyClueAttachmentOut,
    ContentTemplateOut,
)
from ..services.property_clue_service import PropertyClueService

router = Router(tags=["PropertyClue"])


def _get_property_clue_service() -> PropertyClueService:
    """
    工厂函数：创建 PropertyClueService 实例
    
    遵循三层架构规范：
    - API 层通过工厂函数创建服务实例
    - 未来可在此处注入依赖
    """
    return PropertyClueService()



@router.post("/clients/{client_id}/property-clues", response=PropertyClueOut)
def create_property_clue(request, client_id: int, payload: PropertyClueIn):
    """
    创建财产线索
    
    API 层职责：
    1. 参数验证（通过 Schema 自动完成）
    2. 调用 Service 方法
    3. 返回响应
    
    Requirements: 1.1
    """
    service = _get_property_clue_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    
    clue = service.create_clue(
        client_id=client_id,
        data=payload.dict(),
        user=user
    )
    
    return clue


@router.get("/clients/{client_id}/property-clues", response=List[PropertyClueOut])
def list_property_clues(request, client_id: int):
    """
    获取当事人的所有财产线索
    
    API 层职责：
    1. 接收路径参数
    2. 调用 Service
    3. 返回结果列表
    
    Requirements: 4.1
    """
    service = _get_property_clue_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    
    clues = service.list_clues_by_client(
        client_id=client_id,
        user=user
    )
    
    return list(clues)


@router.get("/property-clues/{clue_id}", response=PropertyClueOut)
def get_property_clue(request, clue_id: int):
    """
    获取单个财产线索详情
    
    API 层职责：
    1. 接收路径参数
    2. 调用 Service
    3. 返回结果
    
    Requirements: 1.1
    """
    service = _get_property_clue_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    
    clue = service.get_clue(
        clue_id=clue_id,
        user=user
    )
    
    return clue


@router.put("/property-clues/{clue_id}", response=PropertyClueOut)
def update_property_clue(request, clue_id: int, payload: PropertyClueUpdateIn):
    """
    更新财产线索
    
    API 层职责：
    1. 接收参数
    2. 调用 Service
    3. 返回结果
    
    Requirements: 5.1
    """
    service = _get_property_clue_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    
    # 只传递非空字段
    data = payload.dict(exclude_unset=True)
    
    clue = service.update_clue(
        clue_id=clue_id,
        data=data,
        user=user
    )
    
    return clue


@router.delete("/property-clues/{clue_id}", response={204: None})
def delete_property_clue(request, clue_id: int):
    """
    删除财产线索
    
    API 层职责：
    1. 接收参数
    2. 调用 Service
    3. 返回 204 状态码
    
    Requirements: 5.2
    """
    service = _get_property_clue_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    
    service.delete_clue(
        clue_id=clue_id,
        user=user
    )
    
    return 204, None



@router.post("/property-clues/{clue_id}/attachments", response=PropertyClueAttachmentOut)
def upload_attachment(
    request,
    clue_id: int,
    file: UploadedFile = File(...)
):
    """
    为财产线索上传附件
    
    API 层职责：
    1. 接收文件上传
    2. 处理文件存储（UI 相关逻辑）
    3. 调用 Service 创建附件记录
    4. 返回响应
    
    Requirements: 3.1
    """
    service = _get_property_clue_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    
    # 处理文件上传（UI 相关逻辑，保留在 API 层）
    base_dir = os.path.join(settings.MEDIA_ROOT, "property_clue_attachments", str(clue_id))
    os.makedirs(base_dir, exist_ok=True)
    
    target_path = os.path.join(base_dir, file.name)
    with open(target_path, "wb+") as f:
        for chunk in file.chunks():
            f.write(chunk)
    
    # 调用 Service 创建附件记录
    attachment = service.add_attachment(
        clue_id=clue_id,
        file_path=os.path.abspath(target_path),
        file_name=file.name,
        user=user
    )
    
    return attachment


@router.delete("/property-clue-attachments/{attachment_id}", response={204: None})
def delete_attachment(request, attachment_id: int):
    """
    删除财产线索附件
    
    API 层职责：
    1. 接收参数
    2. 调用 Service
    3. 返回 204 状态码
    
    Requirements: 5.3
    """
    service = _get_property_clue_service()
    user = getattr(request, 'auth', None) or getattr(request, 'user', None)
    
    service.delete_attachment(
        attachment_id=attachment_id,
        user=user
    )
    
    return 204, None



@router.get("/property-clues/content-template", response=ContentTemplateOut)
def get_content_template(request, clue_type: str):
    """
    获取内容模板
    
    API 层职责：
    1. 接收查询参数
    2. 调用 Service 静态方法
    3. 返回模板
    
    Requirements: 2.1, 2.2, 2.3, 2.4
    """
    template = PropertyClueService.get_content_template(clue_type)
    
    return ContentTemplateOut(
        clue_type=clue_type,
        template=template
    )
