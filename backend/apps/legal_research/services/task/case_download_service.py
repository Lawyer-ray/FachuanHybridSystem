"""案例下载服务"""

from __future__ import annotations

import logging
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from apps.core.exceptions import ValidationException
from apps.core.filesystem.upload_paths import MediaEntity
from apps.core.security.secret_codec import SecretCodec
from apps.core.services.storage_service import to_media_abs
from apps.legal_research.models import (
    CaseDownloadFormat,
    CaseDownloadResult,
    CaseDownloadResultStatus,
    CaseDownloadStatus,
    CaseDownloadTask,
)
from apps.legal_research.services.executor_components.task_lifecycle import ExecutorTaskLifecycleMixin
from apps.legal_research.services.sources import get_case_source_client
from apps.legal_research.services.sources.weike import WeikeCaseClient, WeikeSession

logger = logging.getLogger(__name__)

# 逐案循环与同步 Playwright 交错：open_session 之后本线程挂着运行中循环，直连
# sync ORM 会抛 SynchronousOnlyOperation，ORM 写统一经 _run_orm_safely 摆渡
# （无循环时原样内联执行，行为不变）。
_orm = ExecutorTaskLifecycleMixin._run_orm_safely


def _safe_case_number(case_number: str) -> str:
    """清洗案号中不适合做文件名的字符。"""
    return re.sub(r'[\\\\/:*?"<>|]+', "_", case_number).strip("._ ")


class CaseDownloadService:  # pragma: no cover
    """案例下载服务"""

    @classmethod
    def _task_files_rel_dir(cls, task_id: int) -> str:
        """任务判决书文件在 media 下的相对目录"""
        return f"{MediaEntity.LEGAL_RESEARCH}/case_download/{task_id}"

    @classmethod
    def parse_case_numbers(cls, text: str) -> list[str]:  # pragma: no cover
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
    def create_task(  # pragma: no cover
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
    def execute_task(cls, *, task_id: int) -> dict[str, Any]:  # pragma: no cover
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
        task.started_at = timezone.now()
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
            source_client = get_case_source_client("weike")  # type: ignore[assignment]
            session = source_client.open_session(  # type: ignore[union-attr]
                username=credential.account,
                password=SecretCodec().try_decrypt(credential.password),
                login_url=credential.url or None,
            )

            for i, case_number in enumerate(case_numbers, 1):
                # 每 5 次循环或首尾更新一次进度消息（减少 DB 写入频率）
                if i == 1 or i == len(case_numbers) or i % 5 == 0:
                    task.message = f"正在下载 {i}/{len(case_numbers)}: {case_number}"
                    _orm(lambda: task.save(update_fields=["message", "updated_at"]))

                try:
                    result_data = cls._download_single_case(
                        client=source_client,  # type: ignore[arg-type]
                        session=session,
                        case_number=case_number,
                        file_format=file_format,
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

            task.finished_at = timezone.now()
            _orm(
                lambda: task.save(
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
            task.finished_at = timezone.now()
            _orm(lambda: task.save(update_fields=["status", "error", "finished_at", "updated_at"]))
            return {"status": "failed", "error": str(exc)}

        finally:
            if session is not None:
                session.close()

    @classmethod
    def _download_single_case(  # pragma: no cover
        cls,
        *,
        client: WeikeCaseClient,
        session: WeikeSession,
        case_number: str,
        file_format: str,
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
            _orm(
                lambda: CaseDownloadResult.objects.create(
                    task=task,
                    case_number=case_number,
                    status=CaseDownloadResultStatus.FAILED,
                    error_message="未找到案例",
                    file_format=file_format,
                )
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
            _orm(
                lambda: CaseDownloadResult.objects.create(
                    task=task,
                    case_number=case_number,
                    title=detail.title,
                    court=detail.court_text,
                    judgment_date=detail.judgment_date,
                    status=CaseDownloadResultStatus.FAILED,
                    error_message="下载失败",
                    file_format=file_format,
                )
            )
            return {"success": False, "error": "下载失败"}

        file_bytes, original_filename = result

        # 4. 保存文件（按案号重命名，落库存 media 相对路径）
        extension = "pdf" if file_format == CaseDownloadFormat.PDF else "doc"
        file_name = f"{_safe_case_number(case_number)}.{extension}"
        rel_path = f"{cls._task_files_rel_dir(task.id)}/{file_name}"
        saved_name = default_storage.save(rel_path, ContentFile(file_bytes))

        # 5. 保存结果
        _orm(
            lambda: CaseDownloadResult.objects.create(
                task=task,
                case_number=case_number,
                title=detail.title,
                court=detail.court_text,
                judgment_date=detail.judgment_date,
                file_path=saved_name,
                file_size=len(file_bytes),
                file_format=file_format,
                status=CaseDownloadResultStatus.SUCCESS,
            )
        )

        return {"success": True, "file_path": saved_name}

    @classmethod
    def download_task_as_zip(cls, *, task_id: int) -> tuple[Path | None, str]:  # pragma: no cover
        """打包任务所有文件为 zip"""
        return cls.download_tasks_as_zip(task_ids=[task_id])

    @classmethod
    def download_tasks_as_zip(cls, *, task_ids: list[int]) -> tuple[Path | None, str]:  # pragma: no cover
        """打包一个或多个任务的判决书为 zip（admin 单任务/批量共用本实现）。

        zip 在系统临时目录打包后经 default_storage 保存到
        ``legal_research/case_download`` 下，返回 zip 的绝对路径。
        """
        tasks = list(CaseDownloadTask.objects.filter(id__in=task_ids))
        if not tasks:
            return None, "任务不存在"

        results = CaseDownloadResult.objects.filter(task_id__in=task_ids, status=CaseDownloadResultStatus.SUCCESS)
        if not results.exists():
            return None, "没有可下载的文件"

        single_task_id = tasks[0].id if len(tasks) == 1 else None
        zip_stem = str(single_task_id) if single_task_id is not None else "批量"
        zip_filename = f"案例下载_{zip_stem}_{timezone.now().strftime('%Y%m%d%H%M%S')}.zip"
        packed = 0

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_zip = Path(tmp_dir) / zip_filename
            with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                for result in results.select_related("task"):
                    try:
                        file_path = to_media_abs(result.file_path)
                    except ValidationException:
                        logger.warning("跳过不在 MEDIA_ROOT 内的结果文件", extra={"result_id": result.pk})
                        continue
                    if not file_path.exists():
                        continue
                    # 使用案号作为文件名（多任务时按任务 ID 分目录）
                    safe_name = _safe_case_number(result.case_number)
                    ext = file_path.suffix.lstrip(".")
                    arc_name = f"{safe_name}.{ext}" if single_task_id else f"{result.task_id}/{safe_name}.{ext}"
                    zf.write(file_path, arc_name)
                    packed += 1

            if packed == 0:
                return None, "文件不存在或已被清理"
            rel_path = f"{MediaEntity.LEGAL_RESEARCH}/case_download/{zip_filename}"
            saved_name = default_storage.save(rel_path, ContentFile(tmp_zip.read_bytes()))

        logger.info("案例下载 zip 已生成", extra={"task_ids": task_ids, "files": packed, "zip": saved_name})
        return to_media_abs(saved_name), f"共 {packed} 个文件"

    @classmethod
    def delete_task_files(cls, *, task_id: int) -> int:  # pragma: no cover
        """删除任务的所有文件，返回删除的文件数"""
        try:
            task_dir = to_media_abs(cls._task_files_rel_dir(task_id))
        except ValidationException:
            logger.warning("任务文件目录路径无效", extra={"task_id": task_id})
            return 0
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
            logger.debug("删除任务目录失败（已忽略）", exc_info=True)
            pass

        return count
