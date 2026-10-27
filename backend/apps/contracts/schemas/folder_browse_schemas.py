"""合同绑定文件夹浏览 API Schemas（与案件域的 CaseFolderBrowse 契约同形）。"""

from __future__ import annotations

from ninja import Schema

__all__: list[str] = [
    "ContractFolderSubfolderOut",
    "ContractFolderFileOut",
    "ContractFolderEntriesOut",
    "ContractFolderEntryNameIn",
    "ContractFolderCopyIn",
    "ContractFolderPathIn",
    "ContractFolderSaveIn",
    "ContractFolderSaveOut",
    "ContractFolderSaveAsIntentIn",
    "ContractFolderSaveAsIntentOut",
]


class ContractFolderSubfolderOut(Schema):
    name: str
    """绑定根下的相对路径（posix，不含开头斜杠），下钻时原样回传"""

    subpath: str
    """子目录下**一层**文件数；前端据此判断常法「服务事项是否已交付」"""
    file_count: int = 0


class ContractFolderFileOut(Schema):
    name: str
    subpath: str
    size: int
    modified_at: str


class ContractFolderEntriesOut(Schema):
    browsable: bool
    message: str | None = None
    path_display: str = ""
    subpath: str = ""
    parent_subpath: str = ""
    folders: list[ContractFolderSubfolderOut] = []
    files: list[ContractFolderFileOut] = []


class ContractFolderEntryNameIn(Schema):
    """新建 / 重命名共用入参：subpath 定位目标（mkdir 为父目录、rename 为条目本身），name 为新名字。"""

    subpath: str = ""
    name: str


class ContractFolderCopyIn(Schema):
    """复制入参：subpath 为复制源，dest_subpath 为目标目录（空 = 绑定根）。"""

    subpath: str
    dest_subpath: str = ""


class ContractFolderPathIn(Schema):
    """删除入参：subpath 定位要移入回收目录的条目。"""

    subpath: str


class ContractFolderSaveIn(Schema):
    """原地保存入参：subpath 定位文件，expect_mtime 做乐观锁。

    content 走 multipart 字段 `file`（二进制不能塞 JSON），mtime 走表单字段。
    单独定 schema 只为说明语义边界：这是**覆盖写**，与上传的「不覆盖」相反。
    """

    subpath: str
    # 打开时该文件的 mtime（秒）。缺省不校验——只在明确要防并发时传。
    expect_mtime: float | None = None


class ContractFolderSaveOut(Schema):
    """保存结果：新 subpath/文件名/大小/mtime（前端据此更新状态）。"""

    subpath: str
    name: str
    size: int = 0
    modified_at: str | None = None


class ContractFolderSaveAsIntentIn(Schema):
    """登记「下次保存要另存为」意图的入参。

    **不是写文件接口**：编辑后的字节只在 OnlyOffice 那边（社区版不暴露
    downloadAs），这里只把「另存为新名字」这个决定记到编辑器会话上，
    真正的落盘由 DS 保存回调完成。
    """

    subpath: str
    """源文件在绑定根下的相对路径（用来反查是哪一份会话）"""

    name: str
    """新文件名（前端默认给 `原名[修订版]V1_日期.docx`；后端会再清洗一遍）"""


class ContractFolderSaveAsIntentOut(Schema):
    """登记结果。

    `registered=False` 不走这条路（找不到会话直接抛 404）；保留字段是为了
    前端能统一处理，将来若要支持「会话存在但已被其它保存消费」之类状态不用改契约。
    """

    registered: bool = True
    name: str
    """实际登记的文件名（已清洗，可能与入参不同）"""

    subpath: str
    """源文件路径（回显，方便前端核对是哪一份）"""
