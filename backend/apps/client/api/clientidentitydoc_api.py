from django.conf import settings
import os
from ninja import Router, File, Form
from ninja.files import UploadedFile
from ..models import ClientIdentityDoc, Client

router = Router()


def _get_identity_doc_service():
    """工厂函数：创建 ClientIdentityDocService 实例"""
    from ..services import ClientIdentityDocService
    return ClientIdentityDocService()


def _get_client_service():
    """工厂函数：创建 ClientService 实例"""
    from ..services import ClientService
    return ClientService()


@router.post("/clients/{client_id}/identity-docs")
def add_identity_doc(request, client_id: int, doc_type: str, file: UploadedFile = File(...)):
    """
    添加证件文档
    
    Args:
        request: HTTP 请求
        client_id: 客户 ID
        doc_type: 证件类型
        file: 上传的文件
        
    Returns:
        操作结果
    """
    # 1. 处理文件存储（API 层职责）
    base_dir = os.path.join(settings.MEDIA_ROOT, "client_docs", str(client_id))
    os.makedirs(base_dir, exist_ok=True)
    target_path = os.path.join(base_dir, file.name)
    
    with open(target_path, "wb+") as f:
        for chunk in file.chunks():
            f.write(chunk)
    
    # 2. 委托给 Service 层处理业务逻辑
    service = _get_identity_doc_service()
    identity_doc = service.add_identity_doc(
        client_id=client_id,
        doc_type=doc_type,
        file_path=os.path.abspath(target_path),
        user=getattr(request, 'user', None)
    )
    
    return {
        "success": True,
        "doc_id": identity_doc.id,
        "message": "证件文档添加成功"
    }


@router.get("/identity-docs/{doc_id}")
def get_identity_doc(request, doc_id: int):
    """
    获取证件文档
    
    Args:
        request: HTTP 请求
        doc_id: 证件文档 ID
        
    Returns:
        证件文档信息
    """
    service = _get_identity_doc_service()
    identity_doc = service.get_identity_doc(doc_id)
    
    return {
        "id": identity_doc.id,
        "client_id": identity_doc.client_id,
        "doc_type": identity_doc.doc_type,
        "file_path": identity_doc.file_path,
        "created_at": identity_doc.created_at.isoformat() if hasattr(identity_doc, 'created_at') else None,
        "updated_at": identity_doc.updated_at.isoformat() if hasattr(identity_doc, 'updated_at') else None
    }


@router.delete("/identity-docs/{doc_id}")
def delete_identity_doc(request, doc_id: int):
    """
    删除证件文档
    
    Args:
        request: HTTP 请求
        doc_id: 证件文档 ID
        
    Returns:
        操作结果
    """
    service = _get_identity_doc_service()
    service.delete_identity_doc(
        doc_id=doc_id,
        user=getattr(request, 'user', None)
    )
    
    return {
        "success": True,
        "message": "证件文档删除成功"
    }


@router.api_operation(["GET", "POST"], "/parse-text")
def parse_text_any(request):
    """
    解析客户文本
    
    Args:
        request: HTTP 请求
        
    Returns:
        解析后的客户数据
    """
    text = request.GET.get("text") or request.POST.get("text") or ""
    
    # 委托给 ClientService 处理文本解析
    service = _get_client_service()
    parsed_data = service.parse_client_text(text)
    
    return parsed_data
