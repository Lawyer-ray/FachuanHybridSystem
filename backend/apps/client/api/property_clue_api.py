"""
财产线索 API 层
只负责请求/响应处理，不包含业务逻辑
"""

from typing import Any

from ninja import File, Router
from ninja.files import UploadedFile

from apps.client.schemas import (
    ContentTemplateOut,
    PropertyClueAttachmentOut,
    PropertyClueIn,
    PropertyClueOut,
    PropertyClueUpdateIn,
)

router = Router(tags=["PropertyClue"])


def _get_property_clue_service() -> Any:
    """工厂函数：创建 PropertyClueService 实例（延迟导入）"""
    from apps.client.services.property_clue_service import PropertyClueService

    return PropertyClueService()


@router.post("/clients/{client_id}/property-clues", response=PropertyClueOut)
def create_property_clue(request: Any, client_id: int, payload: PropertyClueIn) -> Any:
    """
    创建财产线索

    API 层职责：
    1. 参数验证（通过 Schema 自动完成）
    2. 调用 Service 方法
    3. 返回响应

    Requirements: 1.1
    """
    service = _get_property_clue_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)

    clue = service.create_clue(client_id=client_id, data=payload.model_dump(), user=user)

    return clue


@router.get("/clients/{client_id}/property-clues", response=list[PropertyClueOut])
def list_property_clues(request: Any, client_id: int) -> Any:
    """
    获取当事人的所有财产线索

    API 层职责：
    1. 接收路径参数
    2. 调用 Service
    3. 返回结果列表

    Requirements: 4.1
    """
    service = _get_property_clue_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)

    clues = service.list_clues_by_client(client_id=client_id, user=user)

    return list(clues)


@router.get("/property-clues/content-template", response=ContentTemplateOut)
def get_content_template(request: Any, clue_type: str) -> ContentTemplateOut:
    """
    获取内容模板

    API 层职责：
    1. 接收查询参数
    2. 调用 Service 静态方法
    3. 返回模板

    Requirements: 2.1, 2.2, 2.3, 2.4
    """
    template = _get_property_clue_service().get_content_template(clue_type)

    return ContentTemplateOut(clue_type=clue_type, template=template)


@router.get("/property-clues/{clue_id}", response=PropertyClueOut)
def get_property_clue(request: Any, clue_id: int) -> Any:
    """
    获取单个财产线索详情

    API 层职责：
    1. 接收路径参数
    2. 调用 Service
    3. 返回结果

    Requirements: 1.1
    """
    service = _get_property_clue_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)

    clue = service.get_clue(clue_id=clue_id, user=user)

    return clue


@router.put("/property-clues/{clue_id}", response=PropertyClueOut)
def update_property_clue(request: Any, clue_id: int, payload: PropertyClueUpdateIn) -> Any:
    """
    更新财产线索

    API 层职责：
    1. 接收参数
    2. 调用 Service
    3. 返回结果

    Requirements: 5.1
    """
    service = _get_property_clue_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)

    # 只传递非空字段
    data = payload.model_dump(exclude_unset=True)

    clue = service.update_clue(clue_id=clue_id, data=data, user=user)

    return clue


@router.delete("/property-clues/{clue_id}", response={204: None})
def delete_property_clue(request: Any, clue_id: int) -> tuple[int, None]:
    """
    删除财产线索

    API 层职责：
    1. 接收参数
    2. 调用 Service
    3. 返回 204 状态码

    Requirements: 5.2
    """
    service = _get_property_clue_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)

    service.delete_clue(clue_id=clue_id, user=user)

    return 204, None


@router.post("/property-clues/{clue_id}/attachments", response=PropertyClueAttachmentOut)
def upload_attachment(
    request: Any,
    clue_id: int,
    file: UploadedFile = File(...),  # type: ignore[arg-type]
) -> Any:
    """为财产线索上传附件"""
    service = _get_property_clue_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    return service.add_attachment_from_upload(clue_id=clue_id, uploaded_file=file, user=user)


@router.delete("/property-clue-attachments/{attachment_id}", response={204: None})
def delete_attachment(request: Any, attachment_id: int) -> tuple[int, None]:
    """
    删除财产线索附件

    API 层职责：
    1. 接收参数
    2. 调用 Service
    3. 返回 204 状态码

    Requirements: 5.3
    """
    service = _get_property_clue_service()
    user = getattr(request, "auth", None) or getattr(request, "user", None)

    service.delete_attachment(attachment_id=attachment_id, user=user)

    return 204, None


