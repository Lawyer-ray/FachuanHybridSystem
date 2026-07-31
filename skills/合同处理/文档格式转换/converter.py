"""
文档格式转换 Skill

将 .doc 文件转换为 .docx 格式。
调用后端 API 实现，底层使用 LibreOffice。
"""

import logging
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# API 配置
API_BASE_URL = "http://127.0.0.1:8002/api/v1/doc-converter"
POLL_INTERVAL = 1.5  # 轮询间隔（秒）
MAX_WAIT_TIME = 3600  # 最大等待时间（秒）


def check_health() -> bool:
    """检查 LibreOffice 是否可用

    Returns:
        是否可用
    """
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        return response.status_code == 200 and response.json().get("libreoffice_available", False)
    except Exception as e:
        logger.error("健康检查失败: %s", str(e))
        return False


def create_conversion_job(file_paths: list[str | Path]) -> dict:
    """创建转换任务

    Args:
        file_paths: .doc 文件路径列表

    Returns:
        任务信息字典
    """
    files = []
    for path in file_paths:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        if path.suffix.lower() != '.doc':
            raise ValueError(f"不支持的文件格式: {path.suffix}，仅支持 .doc")
        files.append(("files", (path.name, open(path, "rb"), "application/msword")))

    try:
        response = requests.post(f"{API_BASE_URL}/jobs", files=files, timeout=30)
        response.raise_for_status()
        return response.json()
    finally:
        for _, (_, file_obj, _) in files:
            file_obj.close()


def get_job_progress(job_id: str) -> dict:
    """获取任务进度

    Args:
        job_id: 任务 ID

    Returns:
        任务进度信息
    """
    response = requests.get(f"{API_BASE_URL}/jobs/{job_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def download_converted_files(job_id: str, output_dir: str | Path) -> Path:
    """下载转换后的文件

    Args:
        job_id: 任务 ID
        output_dir: 输出目录

    Returns:
        ZIP 文件路径
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    response = requests.get(f"{API_BASE_URL}/jobs/{job_id}/download", timeout=60, stream=True)
    response.raise_for_status()

    zip_path = output_dir / f"converted_{job_id[:8]}.zip"
    with open(zip_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return zip_path


def delete_job(job_id: str) -> bool:
    """删除任务

    Args:
        job_id: 任务 ID

    Returns:
        是否成功
    """
    try:
        response = requests.delete(f"{API_BASE_URL}/jobs/{job_id}", timeout=10)
        return response.status_code == 200
    except Exception:
        return False


def convert_doc_to_docx(
    input_paths: list[str | Path],
    output_dir: str | Path | None = None,
    keep_job: bool = False
) -> dict:
    """
    将 .doc 文件转换为 .docx 格式

    Args:
        input_paths: .doc 文件路径列表
        output_dir: 输出目录（可选，默认为第一个文件所在目录）
        keep_job: 是否保留服务器上的任务（调试用）

    Returns:
        转换结果字典
    """
    # 检查 LibreOffice
    if not check_health():
        return {
            'success': False,
            'error': 'LibreOffice 不可用，请检查服务器配置'
        }

    # 验证输入文件
    valid_paths = []
    for path in input_paths:
        path = Path(path)
        if not path.exists():
            logger.warning("文件不存在，跳过: %s", path)
            continue
        if path.suffix.lower() != '.doc':
            logger.warning("不是 .doc 文件，跳过: %s", path)
            continue
        valid_paths.append(path)

    if not valid_paths:
        return {
            'success': False,
            'error': '没有有效的 .doc 文件'
        }

    # 确定输出目录
    if output_dir is None:
        output_dir = valid_paths[0].parent
    output_dir = Path(output_dir)

    # 创建转换任务
    logger.info("创建转换任务，共 %d 个文件...", len(valid_paths))
    try:
        job_result = create_conversion_job(valid_paths)
    except Exception as e:
        return {
            'success': False,
            'error': f'创建任务失败: {str(e)}'
        }

    job_id = job_result.get("job_id")
    if not job_id:
        return {
            'success': False,
            'error': f'创建任务失败: {job_result}'
        }

    logger.info("任务已创建: %s", job_id)

    # 轮询等待完成
    start_time = time.time()
    while True:
        elapsed = time.time() - start_time
        if elapsed > MAX_WAIT_TIME:
            return {
                'success': False,
                'error': f'转换超时（超过 {MAX_WAIT_TIME} 秒）',
                'job_id': job_id
            }

        try:
            progress = get_job_progress(job_id)
        except Exception as e:
            logger.warning("获取进度失败: %s", str(e))
            time.sleep(POLL_INTERVAL)
            continue

        status = progress.get("status")
        progress_pct = progress.get("progress", 0)
        converted = progress.get("converted_files", 0)
        total = progress.get("total_files", 0)

        logger.info("进度: %d%% (%d/%d)", progress_pct, converted, total)

        if status == "COMPLETED":
            break
        elif status in ("FAILED", "CANCELLED"):
            error_msg = progress.get("error", "未知错误")
            return {
                'success': False,
                'error': f'转换失败: {error_msg}',
                'job_id': job_id
            }

        time.sleep(POLL_INTERVAL)

    # 下载结果
    logger.info("下载转换结果...")
    try:
        zip_path = download_converted_files(job_id, output_dir)
    except Exception as e:
        return {
            'success': False,
            'error': f'下载失败: {str(e)}',
            'job_id': job_id
        }

    # 清理任务
    if not keep_job:
        delete_job(job_id)

    # 解压 ZIP
    import zipfile
    extract_dir = output_dir / "converted_docx"
    extract_dir.mkdir(exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

    # 获取转换后的文件列表
    converted_files = list(extract_dir.glob("*.docx"))

    logger.info("转换完成！共 %d 个文件", len(converted_files))

    return {
        'success': True,
        'job_id': job_id,
        'input_files': [str(p) for p in valid_paths],
        'output_dir': str(extract_dir),
        'zip_path': str(zip_path),
        'converted_files': [str(f) for f in converted_files],
        'total_files': len(valid_paths),
        'converted_count': len(converted_files),
    }
