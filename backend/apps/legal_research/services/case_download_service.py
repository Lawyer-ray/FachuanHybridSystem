"""案例下载服务"""

from __future__ import annotations

import logging
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.legal_research.models import CaseDownloadFormat, CaseDownloadResult, CaseDownloadStatus, CaseDownloadTask
from apps.legal_research.services.sources import CaseDetail, get_case_source_client
from apps.legal_research.services.sources.weike import WeikeCaseClient, WeikeSession

logger = logging.getLogger(__name__)


class CaseDownloadService:
    """案例下载服务"""

    DOWNLOAD_DIR = Path(settings.MEDIA_ROOT) / "legal_research" / "case_download"

    @classmethod
    def parse_case_numbers(cls, text: str) -> list[str]:
        """解析案号列表，支持换行、逗号、分号分隔"""
        if not text:
            return []
        # 按换行、逗号、分号分割
        parts = re.split(r"[\n,，;；]+", text)
        case_numbers = []
        for part in parts:
            case_number = part.strip()
            if case_number:
                case_numbers.append(case_number)
        return case_numbers

    @classmethod
    def create_task(
        cls,
        *,
        created_by: Any,
        credential: Any,
        case_numbers_text: str,
        file_format: str = "pdf",
    ) -> CaseDownloadTask:
        """创建下载任务"""
        case_numbers = cls.parse_case_numbers(case_numbers_text)
        task = CaseDownloadTask.objects.create(
            created_by=created_by,
            credential=credential,
            case_numbers=case_numbers_text,
            file_format=file_format,
            status=CaseDownloadStatus.PENDING,
            total_count=len(case_numbers),
        )
        return task

    @classmethod
    def execute_task(cls, *, task_id: int) -> dict[str, Any]:
        """执行下载任务"""
        try:
            task = CaseDownloadTask.objects.get(id=task_id)
        except CaseDownloadTask.DoesNotExist:
            logger.error("案例下载任务不存在", extra={"task_id": task_id})
            return {"status": "failed", "error": "任务不存在"}

        if task.status in (CaseDownloadStatus.COMPLETED, CaseDownloadStatus.RUNNING):
            logger.warning("任务状态不允许执行", extra={"task_id": task_id, "status": task.status})
            return {"status": "skipped", "error": "任务状态不允许执行"}

        task.status = CaseDownloadStatus.RUNNING
        task.started_at = datetime.now()
        task.save(update_fields=["status", "started_at", "updated_at"])

        case_numbers = cls.parse_case_numbers(task.case_numbers)
        credential = task.credential
        file_format = task.file_format

        source_client: WeikeCaseClient | None = None
        session: WeikeSession | None = None
        success_count = 0
        failed_count = 0
        errors: list[str] = []

        try:
            source_client = get_case_source_client("weike")
            session = source_client.open_session(
                username=credential.account,
                password=credential.password,
                login_url=credential.url or None,
            )

            task_dir = cls.DOWNLOAD_DIR / str(task.id)
            task_dir.mkdir(parents=True, exist_ok=True)

            for i, case_number in enumerate(case_numbers, 1):
                task.message = f"正在下载 {i}/{len(case_numbers)}: {case_number}"
                task.save(update_fields=["message", "updated_at"])

                try:
                    result_data = cls._download_single_case(
                        client=source_client,
                        session=session,
                        case_number=case_number,
                        file_format=file_format,
                        task_dir=task_dir,
                        task=task,
                    )
                    if result_data["success"]:
                        success_count += 1
                    else:
                        failed_count += 1
                        errors.append(f"{case_number}: {result_data.get('error', '未知错误')}")
                except Exception as exc:
                    failed_count += 1
                    errors.append(f"{case_number}: {exc}")
                    logger.exception("下载单个案例失败", extra={"case_number": case_number})

            task.success_count = success_count
            task.failed_count = failed_count

            if failed_count == 0:
                task.status = CaseDownloadStatus.COMPLETED
                task.message = f"全部下载完成，共 {success_count} 个"
            elif success_count == 0:
                task.status = CaseDownloadStatus.FAILED
                task.message = "全部下载失败"
                task.error = "; ".join(errors[:10])
            else:
                task.status = CaseDownloadStatus.COMPLETED
                task.message = f"部分成功 {success_count}/{len(case_numbers)}"

            task.finished_at = datetime.now()
            task.save(
                update_fields=[
                    "status",
                    "message",
                    "error",
                    "success_count",
                    "failed_count",
                    "finished_at",
                    "updated_at",
                ]
            )

            return {
                "status": task.status,
                "success_count": success_count,
                "failed_count": failed_count,
                "errors": errors,
            }

        except Exception as exc:
            logger.exception("案例下载任务失败", extra={"task_id": task_id})
            task.status = CaseDownloadStatus.FAILED
            task.error = str(exc)
            task.finished_at = datetime.now()
            task.save(update_fields=["status", "error", "finished_at", "updated_at"])
            return {"status": "failed", "error": str(exc)}

        finally:
            if session is not None:
                session.close()

    @classmethod
    def _download_single_case(
        cls,
        *,
        client: WeikeCaseClient,
        session: WeikeSession,
        case_number: str,
        file_format: str,
        task_dir: Path,
        task: CaseDownloadTask,
    ) -> dict[str, Any]:
        """下载单个案例"""
        # 1. 搜索案例
        items = client.search_cases(
            session=session,
            keyword=case_number,
            max_candidates=5,
            max_pages=2,
        )

        if not items:
            CaseDownloadResult.objects.create(
                task=task,
                case_number=case_number,
                status="failed",
                error_message="未找到案例",
                file_format=file_format,
            )
            return {"success": False, "error": "未找到案例"}

        # 2. 获取详情
        item = items[0]
        detail = client.fetch_case_detail(session=session, item=item)

        # 3. 下载文件
        if file_format == CaseDownloadFormat.PDF:
            result = client.download_pdf(session=session, detail=detail)
        elif file_format == CaseDownloadFormat.DOC:
            result = client.download_doc(session=session, detail=detail)
        else:
            return {"success": False, "error": f"不支持的格式: {file_format}"}

        if not result:
            CaseDownloadResult.objects.create(
                task=task,
                case_number=case_number,
                title=detail.title,
                court=detail.court_text,
                judgment_date=detail.judgment_date,
                status="failed",
                error_message="下载失败",
                file_format=file_format,
            )
            return {"success": False, "error": "下载失败"}

        file_bytes, original_filename = result

        # 4. 保存文件（按案号重命名）
        safe_case_number = re.sub(r'[\\\\/:*?"<>|]+', "_", case_number).strip("._ ")
        extension = "pdf" if file_format == CaseDownloadFormat.PDF else "doc"
        file_name = f"{safe_case_number}.{extension}"
        file_path = task_dir / file_name

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # 5. 保存结果
        CaseDownloadResult.objects.create(
            task=task,
            case_number=case_number,
            title=detail.title,
            court=detail.court_text,
            judgment_date=detail.judgment_date,
            file_path=str(file_path),
            file_size=len(file_bytes),
            file_format=file_format,
            status="success",
        )

        return {"success": True, "file_path": str(file_path)}

    @classmethod
    def download_single_file(cls, *, result_id: int) -> tuple[Path | None, str]:
        """下载单个文件"""
        try:
            result = CaseDownloadResult.objects.get(id=result_id)
        except CaseDownloadResult.DoesNotExist:
            return None, "结果不存在"

        file_path = Path(result.file_path)
        if not file_path.exists():
            return None, "文件不存在"

        return file_path, result.case_number

    @classmethod
    def download_task_as_zip(cls, *, task_id: int) -> tuple[Path | None, str]:
        """打包任务所有文件为 zip"""
        try:
            task = CaseDownloadTask.objects.get(id=task_id)
        except CaseDownloadTask.DoesNotExist:
            return None, "任务不存在"

        results = task.results.filter(status="success")
        if not results.exists():
            return None, "没有可下载的文件"

        task_dir = cls.DOWNLOAD_DIR / str(task.id)
        if not task_dir.exists():
            return None, "文件目录不存在"

        # 创建 zip
        zip_filename = f"案例下载_{task.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.zip"
        zip_path = cls.DOWNLOAD_DIR / zip_filename

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for result in results:
                file_path = Path(result.file_path)
                if file_path.exists():
                    # 使用案号作为文件名
                    safe_name = re.sub(r'[\\\\/:*?"<>|]+', "_", result.case_number).strip("._ ")
                    ext = file_path.suffix.lstrip(".")
                    zf.write(file_path, f"{safe_name}.{ext}")

        return zip_path, f"共 {results.count()} 个文件"

    @classmethod
    def delete_task_files(cls, *, task_id: int) -> int:
        """删除任务的所有文件，返回删除的文件数"""
        task_dir = cls.DOWNLOAD_DIR / str(task_id)
        if not task_dir.exists():
            return 0

        count = 0
        for file_path in task_dir.iterdir():
            if file_path.is_file():
                file_path.unlink()
                count += 1

        try:
            task_dir.rmdir()
        except OSError:
            pass

        return count
