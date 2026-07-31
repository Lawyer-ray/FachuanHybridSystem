"""
文档格式转换模块

直接调用 LibreOffice 将 .doc 文件转换为 .docx 格式。
"""

import logging
import shutil
import subprocess
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# LibreOffice 超时时间（秒）
CONVERT_TIMEOUT = 60


def find_libreoffice() -> str | None:
    """查找 LibreOffice 可执行文件

    Returns:
        LibreOffice 可执行文件路径，未找到返回 None
    """
    # 1. 检查 PATH 中的 soffice 或 libreoffice
    for cmd in ["soffice", "libreoffice"]:
        path = shutil.which(cmd)
        if path:
            return path

    # 2. macOS 常见路径
    mac_paths = [
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/Applications/OpenOffice.app/Contents/MacOS/soffice",
        Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    for p in mac_paths:
        p = Path(p)
        if p.exists():
            return str(p)

    # 3. Linux 常见路径
    linux_paths = [
        "/usr/bin/libreoffice",
        "/usr/bin/soffice",
        "/usr/local/bin/libreoffice",
        "/snap/bin/libreoffice",
    ]
    for p in linux_paths:
        if Path(p).exists():
            return p

    return None


def check_libreoffice() -> bool:
    """检查 LibreOffice 是否可用

    Returns:
        是否可用
    """
    return find_libreoffice() is not None


def convert_single_file(
    doc_path: str | Path,
    output_dir: str | Path,
    timeout: int = CONVERT_TIMEOUT
) -> Path | None:
    """转换单个 .doc 文件为 .docx

    Args:
        doc_path: .doc 文件路径
        output_dir: 输出目录
        timeout: 超时时间（秒）

    Returns:
        转换后的 .docx 文件路径，失败返回 None
    """
    soffice = find_libreoffice()
    if not soffice:
        logger.error("LibreOffice 不可用")
        return None

    doc_path = Path(doc_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not doc_path.exists():
        logger.error("文件不存在: %s", doc_path)
        return None

    if doc_path.suffix.lower() != '.doc':
        logger.error("不是 .doc 文件: %s", doc_path)
        return None

    # 预期的输出文件名
    expected_output = output_dir / f"{doc_path.stem}.docx"

    # 调用 LibreOffice 转换
    cmd = [
        soffice,
        "--headless",
        "--convert-to", "docx",
        "--outdir", str(output_dir),
        str(doc_path)
    ]

    try:
        logger.info("转换: %s", doc_path.name)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode != 0:
            logger.error("LibreOffice 转换失败: %s", result.stderr)
            return None

        # 检查输出文件是否存在
        if expected_output.exists():
            logger.info("转换成功: %s", expected_output.name)
            return expected_output

        # 尝试查找输出文件（LibreOffice 有时会改变文件名）
        for f in output_dir.glob("*.docx"):
            if f.stem == doc_path.stem or doc_path.stem in f.name:
                logger.info("转换成功: %s", f.name)
                return f

        logger.error("转换后未找到输出文件")
        return None

    except subprocess.TimeoutExpired:
        logger.error("转换超时（%d 秒）: %s", timeout, doc_path.name)
        return None
    except Exception as e:
        logger.error("转换异常: %s", str(e))
        return None


def batch_convert(
    doc_paths: list[str | Path],
    output_dir: str | Path,
    timeout: int = CONVERT_TIMEOUT
) -> list[Path]:
    """批量转换 .doc 文件为 .docx

    Args:
        doc_paths: .doc 文件路径列表
        output_dir: 输出目录
        timeout: 每个文件的超时时间（秒）

    Returns:
        成功转换的 .docx 文件路径列表
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    converted_files = []
    total = len(doc_paths)

    for i, doc_path in enumerate(doc_paths, 1):
        logger.info("[%d/%d] 处理: %s", i, total, Path(doc_path).name)
        result = convert_single_file(doc_path, output_dir, timeout)
        if result:
            converted_files.append(result)

    return converted_files


def create_zip(file_paths: list[str | Path], zip_path: str | Path) -> Path:
    """将文件打包为 ZIP

    Args:
        file_paths: 文件路径列表
        zip_path: ZIP 文件路径

    Returns:
        ZIP 文件路径
    """
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fp in file_paths:
            fp = Path(fp)
            if fp.exists():
                zf.write(fp, fp.name)

    return zip_path


def convert_doc_to_docx(
    input_paths: list[str | Path],
    output_dir: str | Path | None = None,
    create_zip_archive: bool = True
) -> dict:
    """
    将 .doc 文件转换为 .docx 格式

    Args:
        input_paths: .doc 文件路径列表
        output_dir: 输出目录（可选，默认为第一个文件所在目录下的 converted_docx）
        create_zip_archive: 是否创建 ZIP 打包文件

    Returns:
        转换结果字典
    """
    # 检查 LibreOffice
    if not check_libreoffice():
        return {
            'success': False,
            'error': 'LibreOffice 不可用，请安装 LibreOffice'
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
        output_dir = valid_paths[0].parent / "converted_docx"
    output_dir = Path(output_dir)

    # 批量转换
    logger.info("开始转换，共 %d 个文件...", len(valid_paths))
    converted_files = batch_convert(valid_paths, output_dir)

    if not converted_files:
        return {
            'success': False,
            'error': '所有文件转换失败'
        }

    # 创建 ZIP 打包
    zip_path = None
    if create_zip_archive:
        zip_path = output_dir.parent / f"{output_dir.name}.zip"
        create_zip(converted_files, zip_path)
        logger.info("ZIP 打包完成: %s", zip_path)

    logger.info("转换完成！成功 %d/%d 个文件", len(converted_files), len(valid_paths))

    return {
        'success': True,
        'input_files': [str(p) for p in valid_paths],
        'output_dir': str(output_dir),
        'zip_path': str(zip_path) if zip_path else None,
        'converted_files': [str(f) for f in converted_files],
        'total_files': len(valid_paths),
        'converted_count': len(converted_files),
    }
