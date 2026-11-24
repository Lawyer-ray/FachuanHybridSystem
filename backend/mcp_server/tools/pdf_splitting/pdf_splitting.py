"""PDF 拆解 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def create_pdf_split_job(
    file_base64: str,
    filename: str,
    template_key: str = "filing_materials_v1",
    split_mode: str = "content_analysis",
    ocr_profile: str = "balanced",
    source_path: str = "",
) -> dict[str, Any]:
    """上传 PDF 并创建拆解任务。source_path 非空时改为直接读**服务器本地**路径（仅管理员，此时 file_base64/filename 传空串即可，不再走上传）；file_base64 为文件的 base64 编码；split_mode: content_analysis（内容识别拆分）/ page_split（按页拆分）/ manual_split（手动拆分）；ocr_profile: balanced/fast/accurate。返回 job_id。"""
    data: dict[str, Any] = {
        "template_key": template_key,
        "split_mode": split_mode,
        "ocr_profile": ocr_profile,
    }
    if source_path.strip():
        # 二选一，source_path 优先：卷宗已在服务器上时不必把几百 MB 搬进 base64
        data["source_path"] = source_path.strip()
        return client.post("/pdf-splitting/jobs", data=data)  # type: ignore[no-any-return]
    file_bytes = base64.b64decode(file_base64)
    return client.upload(  # type: ignore[no-any-return]
        "/pdf-splitting/jobs",
        files={"file": (filename, file_bytes, "application/pdf")},
        data=data,
    )


def archive_pdf_split_to_case_folder(
    job_id: str,
    case_id: int,
    segments: list[dict[str, Any]],
    date: str = "",
) -> dict[str, Any]:
    """把拆解结果按段切页，直接归档进案件的绑定文件夹（服务端切片 + 命名 + 落盘，不用先下载再上传）。segments 为分段列表，每项四个字段：page_start / page_end（页区间，1 起、含两端）、doc_type（文书名，如“传统起诉状”，进文件名）、material_type（材料类型，一般填任务的 segment_type，决定落哪层子目录）；date 为 YYYYMMDD，留空取今天。返回 {root, written:[{filename, subdir, is_duplicate, absolute_path}], duplicates:[[doc_type, ...]], skipped:[{doc_type, reason}], notice_path}；一式多份的副本由服务端按页指纹判定，默认仍落盘并在 duplicates 里列出。"""
    body: dict[str, Any] = {"case_id": case_id, "segments": segments}
    if date.strip():
        body["date"] = date.strip()
    return client.post(f"/pdf-splitting/jobs/{job_id}/archive-to-case-folder", json=body)  # type: ignore[no-any-return]


def get_pdf_split_job(job_id: str) -> dict[str, Any]:
    """查询 PDF 拆解任务状态和结果。status: pending/processing/review_required/exporting/completed/failed/cancelled。"""
    return client.get(f"/pdf-splitting/jobs/{job_id}")  # type: ignore[no-any-return]


def confirm_pdf_split(job_id: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
    """确认 PDF 拆解分段结果，触发最终打包。segments 为分段列表，每项包含 page_start、page_end、segment_type、filename 等字段。"""
    return client.post(f"/pdf-splitting/jobs/{job_id}/confirm", json={"segments": segments})  # type: ignore[no-any-return]


def cancel_pdf_split(job_id: str) -> dict[str, Any]:
    """取消进行中的 PDF 拆解任务。"""
    return client.post(f"/pdf-splitting/jobs/{job_id}/cancel", json={})  # type: ignore[no-any-return]


def download_pdf_split_result(job_id: str) -> dict[str, Any]:
    """下载 PDF 拆解结果 ZIP 压缩包。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/pdf-splitting/jobs/{job_id}/download")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }


def get_pdf_split_page_preview(job_id: str, page_no: int) -> dict[str, Any]:
    """获取 PDF 拆解任务中某一页的图片预览。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/pdf-splitting/jobs/{job_id}/pages/{page_no}/preview")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }


def download_pdf_split_raw(job_id: str) -> dict[str, Any]:
    """下载 PDF 拆解任务的原始 PDF 文件。返回 {filename, content_type, data_base64}。"""
    content, filename, content_type = client.download(f"/pdf-splitting/jobs/{job_id}/pdf")
    return {
        "filename": filename,
        "content_type": content_type,
        "data_base64": base64.b64encode(content).decode(),
    }
