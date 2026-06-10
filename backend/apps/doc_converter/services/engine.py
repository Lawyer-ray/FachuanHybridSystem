"""LibreOffice doc → docx 转换引擎

从 workbench/services/doc_extractor.py 抽取的纯函数，无实例状态。
调用方负责控制输出目录和清理临时文件。
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from apps.core.services.libreoffice import find_libreoffice

logger = logging.getLogger("apps.doc_converter")

BATCH_CONVERT_SIZE = 25


def convert_single(doc_path: str, output_dir: str, timeout: int = 30) -> str:  # pragma: no cover
    """单个 .doc 转 .docx

    Args:
        doc_path: 源 .doc 文件路径
        output_dir: 输出目录
        timeout: 超时秒数

    Returns:
        转换后的 .docx 文件路径
    """
    soffice = find_libreoffice()
    if not soffice:
        raise RuntimeError("未找到 LibreOffice，无法转换 .doc 文件。请安装 LibreOffice: https://www.libreoffice.org/")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    cmd = [soffice, "--headless", "--convert-to", "docx", "--outdir", output_dir, doc_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    if proc.returncode != 0:
        raise RuntimeError(f"LibreOffice 转换失败: {proc.stderr}")

    doc_name = Path(doc_path).stem + ".docx"
    docx_path = Path(output_dir) / doc_name
    if not docx_path.exists():
        raise FileNotFoundError(f"转换后文件未找到: {docx_path}")

    return str(docx_path)


def batch_convert(
    doc_paths: list[str],
    output_dir: str,
    batch_size: int = BATCH_CONVERT_SIZE,
    timeout: int = 120,
) -> dict[str, str]:  # pragma: no cover
    """批量将 .doc 转换为 .docx

    LibreOffice 支持单次传入多个文件，JVM 启动开销被分摊。

    Args:
        doc_paths: .doc 文件路径列表
        output_dir: 输出目录
        batch_size: 每批文件数
        timeout: 每批超时秒数

    Returns:
        {原始 .doc 路径: 转换后的 .docx 路径}
    """
    if not doc_paths:
        return {}

    soffice = find_libreoffice()
    if not soffice:
        raise RuntimeError("未找到 LibreOffice，无法转换 .doc 文件。请安装 LibreOffice: https://www.libreoffice.org/")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}

    for i in range(0, len(doc_paths), batch_size):
        batch = doc_paths[i : i + batch_size]
        logger.info(
            "LibreOffice 批量转换: 第 %d-%d/%d 个文件",
            i + 1,
            min(i + batch_size, len(doc_paths)),
            len(doc_paths),
        )

        cmd = [soffice, "--headless", "--convert-to", "docx", "--outdir", output_dir] + batch
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if proc.returncode != 0:
                logger.error("LibreOffice 转换失败: %s", proc.stderr)
                for doc_path in batch:
                    try:
                        docx_path = convert_single(doc_path, output_dir)
                        result[doc_path] = docx_path
                    except Exception as e:
                        logger.error("单文件转换失败: %s - %s", doc_path, e)
                continue

            for doc_path in batch:
                doc_name = Path(doc_path).stem + ".docx"
                docx_out = Path(output_dir) / doc_name
                if docx_out.exists():
                    result[doc_path] = str(docx_out)
                else:
                    logger.warning("转换后文件未找到: %s", docx_out)

        except subprocess.TimeoutExpired:
            logger.error("LibreOffice 转换超时")
            for doc_path in batch:
                try:
                    docx_path = convert_single(doc_path, output_dir)
                    result[doc_path] = docx_path
                except Exception as e:
                    logger.error("单文件转换失败: %s - %s", doc_path, e)

    logger.info("批量转换完成: %d/%d 成功", len(result), len(doc_paths))
    return result
