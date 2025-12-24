"""
文书送达数据类

定义文书送达相关的数据传输对象
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


# ============================================================
# API 响应数据类 (来自法院一张网 API)
# ============================================================

@dataclass
class DocumentRecord:
    """
    单个文书记录 - 来自 getSdListByZjhmAndAhdmNew API
    
    对应 Requirements 1.2, 3.1
    """
    ah: str                    # 案号，如"（2025）粤0604民初41257号"
    sdbh: str                  # 送达编号 - 用于获取文书详情
    ajzybh: str                # 案件主要编号
    fssj: str                  # 发送时间，如"2025-12-10 16:25:37" - 用于时间过滤
    fymc: str                  # 法院名称
    ahdm: str = ""             # 案号代码
    fybh: str = ""             # 法院编号
    ssdrxm: str = ""           # 送达人姓名
    ssdrsjhm: str = ""         # 送达人手机号
    ssdrzjhm: str = ""         # 送达人证件号码
    wsmc: str = ""             # 文书名称（多个用逗号分隔）
    sdzt: str = ""             # 送达状态
    qdzt: str = ""             # 签到状态
    qdbh: str = ""             # 签到编号
    fqr: str = ""              # 发起人
    cjsj: str = ""             # 创建时间
    zhxgsj: str = ""           # 最后修改时间
    
    def parse_fssj(self) -> Optional[datetime]:
        """
        解析 fssj（发送时间）字符串为 datetime 对象
        
        Returns:
            datetime 对象，解析失败返回 None
        """
        if not self.fssj:
            return None
        try:
            return datetime.strptime(self.fssj, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            # 尝试其他格式
            try:
                return datetime.fromisoformat(self.fssj)
            except ValueError:
                return None
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "DocumentRecord":
        """从 API 响应字典创建实例"""
        return cls(
            ah=data.get("ah", ""),
            sdbh=data.get("sdbh", ""),
            ajzybh=data.get("ajzybh", ""),
            fssj=data.get("fssj", ""),
            fymc=data.get("fymc", ""),
            ahdm=data.get("ahdm", ""),
            fybh=data.get("fybh", ""),
            ssdrxm=data.get("ssdrxm", ""),
            ssdrsjhm=data.get("ssdrsjhm", ""),
            ssdrzjhm=data.get("ssdrzjhm", ""),
            wsmc=data.get("wsmc", ""),
            sdzt=data.get("sdzt", ""),
            qdzt=data.get("qdzt", ""),
            qdbh=data.get("qdbh", ""),
            fqr=data.get("fqr", ""),
            cjsj=data.get("cjsj", ""),
            zhxgsj=data.get("zhxgsj", ""),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "ah": self.ah,
            "sdbh": self.sdbh,
            "ajzybh": self.ajzybh,
            "fssj": self.fssj,
            "fymc": self.fymc,
            "ahdm": self.ahdm,
            "fybh": self.fybh,
            "ssdrxm": self.ssdrxm,
            "ssdrsjhm": self.ssdrsjhm,
            "ssdrzjhm": self.ssdrzjhm,
            "wsmc": self.wsmc,
            "sdzt": self.sdzt,
            "qdzt": self.qdzt,
            "qdbh": self.qdbh,
            "fqr": self.fqr,
            "cjsj": self.cjsj,
            "zhxgsj": self.zhxgsj,
        }


@dataclass
class DocumentDetail:
    """
    文书详情（下载信息）- 来自 getWsListBySdbhNew API
    
    对应 Requirements 2.2
    """
    c_sdbh: str                # 送达编号
    c_wsmc: str                # 文书名称
    c_wjgs: str                # 文件格式（如 pdf）
    wjlj: str                  # 文件链接（OSS URL，带签名）
    c_stbh: str = ""           # 上传编号（文件路径）
    c_wsbh: str = ""           # 文书编号
    c_fybh: str = ""           # 法院编号
    c_fymc: str = ""           # 法院名称
    dt_cjsj: str = ""          # 创建时间（ISO格式）
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "DocumentDetail":
        """从 API 响应字典创建实例"""
        return cls(
            c_sdbh=data.get("c_sdbh", ""),
            c_wsmc=data.get("c_wsmc", ""),
            c_wjgs=data.get("c_wjgs", ""),
            wjlj=data.get("wjlj", ""),
            c_stbh=data.get("c_stbh", ""),
            c_wsbh=data.get("c_wsbh", ""),
            c_fybh=data.get("c_fybh", ""),
            c_fymc=data.get("c_fymc", ""),
            dt_cjsj=data.get("dt_cjsj", ""),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "c_sdbh": self.c_sdbh,
            "c_wsmc": self.c_wsmc,
            "c_wjgs": self.c_wjgs,
            "wjlj": self.wjlj,
            "c_stbh": self.c_stbh,
            "c_wsbh": self.c_wsbh,
            "c_fybh": self.c_fybh,
            "c_fymc": self.c_fymc,
            "dt_cjsj": self.dt_cjsj,
        }


@dataclass
class DocumentListResponse:
    """
    文书列表 API 响应
    
    对应 Requirements 1.4, 3.4
    """
    total: int                              # data.total - 总数量，用于分页计算
    documents: List[DocumentRecord] = field(default_factory=list)  # data.data - 文书记录列表
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "DocumentListResponse":
        """
        从 API 响应字典创建实例
        
        API 响应格式:
        {
            "code": 200,
            "msg": "成功！",
            "success": true,
            "data": {
                "total": 19,
                "data": [...]
            }
        }
        """
        inner_data = data.get("data", {})
        total = inner_data.get("total", 0)
        documents_data = inner_data.get("data", [])
        
        documents = [
            DocumentRecord.from_api_response(doc)
            for doc in documents_data
        ]
        
        return cls(total=total, documents=documents)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "total": self.total,
            "documents": [doc.to_dict() for doc in self.documents],
        }


# ============================================================
# 原有数据类 (Playwright 方式使用)
# ============================================================

@dataclass
class DocumentDeliveryRecord:
    """文书送达记录"""
    case_number: str           # 案号
    send_time: datetime        # 发送时间
    element_index: int         # 页面元素索引（用于定位下载按钮）
    document_name: str = ""    # 文书名称（可选）
    court_name: str = ""       # 法院名称（可选）
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "case_number": self.case_number,
            "send_time": self.send_time.isoformat() if self.send_time else None,
            "element_index": self.element_index,
            "document_name": self.document_name,
            "court_name": self.court_name
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentDeliveryRecord":
        """从字典反序列化"""
        send_time = None
        if data.get("send_time"):
            if isinstance(data["send_time"], str):
                send_time = datetime.fromisoformat(data["send_time"])
            else:
                send_time = data["send_time"]
        
        return cls(
            case_number=data["case_number"],
            send_time=send_time,
            element_index=data["element_index"],
            document_name=data.get("document_name", ""),
            court_name=data.get("court_name", "")
        )


@dataclass
class DocumentQueryResult:
    """文书查询结果"""
    total_found: int           # 发现的文书总数
    processed_count: int       # 处理的文书数
    skipped_count: int         # 跳过的文书数（时间过滤或已处理）
    failed_count: int          # 处理失败数
    case_log_ids: List[int]    # 创建的案件日志 ID 列表
    errors: List[str]          # 错误信息列表


@dataclass
class DocumentProcessResult:
    """单个文书处理结果"""
    success: bool              # 是否成功
    case_id: Optional[int]     # 匹配的案件ID
    case_log_id: Optional[int] # 创建的案件日志ID
    renamed_path: Optional[str] # 重命名后的文件路径
    notification_sent: bool    # 是否发送了通知
    error_message: Optional[str] # 错误信息