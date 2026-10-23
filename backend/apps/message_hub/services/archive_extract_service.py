"""上传压缩包展开 —— zip/rar/7z 拖进材料预处理台直接变成包内文件。

## 行为

```
材料.zip ─┐
合同.rar ─┼─ expand_upload_files() ─→ [a.pdf, b.jpg, 子目录/c.docx, ...]
发票.7z  ─┘      （压内文件逐个过同一套白名单/限额，展开后与逐个上传等价）
```

- **zip**：stdlib ``zipfile``（所有环境可用）。解压前先读 ``infolist`` 核对
  条目数/单条大小/总大小/压缩比（zip 炸弹防线），再逐条读取。
- **rar / 7z**：``bsdtar``（libarchive）子进程解到临时目录再收集。二进制
  缺失时给明确错误而不是 500；具体格式支持面取决于系统 libarchive 构建。
- **安全**：
  - 路径穿越（zip slip）：条目名清洗为安全的 posix 相对路径，含 ``..``
    或绝对路径成分的条目**直接丢弃并计数**；
  - 容量：单条 ≤ 50MB（与手动上传单文件上限一致）、单包 ≤ 200 条 /
    200MB 未压缩总量、zip 压缩比 > 100 判为炸弹拒绝；
  - 白名单：展开后的内层文件走与直传完全相同的扩展名校验；
  - 嵌套压缩包**不递归**（内层 .zip/.rar/.7z 按普通压缩包附件保留，
    需要时用户可再拖一次）——防一层套一层的放大攻击。
- **噪声清理**：``__MACOSX/``、``.DS_Store``、``Thumbs.db``、
  ``desktop.ini`` 等 OS/压缩工具产物静默跳过。

展开产物是内存 File（与直传的 UploadedFile 同接口、但保留相对路径名），
落盘/页数统计/追加协议零改动。
"""

from __future__ import annotations

import io
import logging
import mimetypes
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from django.core.files.base import File

from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.message_hub")

ARCHIVE_EXTENSIONS = frozenset({".zip", ".rar", ".7z"})

#: 单个压缩包展开后的条目数 / 未压缩总量 / 单条大小上限
MAX_ENTRIES = 200
MAX_TOTAL_BYTES = 200 * 1024 * 1024
MAX_ENTRY_BYTES = 50 * 1024 * 1024
#: zip 炸弹防线：未压缩/已压缩 > 该倍数即拒绝
MAX_COMPRESS_RATIO = 100

#: 系统/压缩工具噪声（不进材料包）
_JUNK_NAMES = {"__MACOSX", ".DS_Store", "Thumbs.db", "desktop.ini"}
_JUNK_PREFIXES = ("__MACOSX/",)


def is_archive_filename(name: str) -> bool:
    return Path(name).suffix.lower() in ARCHIVE_EXTENSIONS


def _sanitize_entry_name(raw: str) -> str | None:
    """压缩包条目名 → 安全 posix 相对路径；不安全（穿越/空/噪声）返回 None。"""
    name = (raw or "").strip().replace("\\", "/")
    if not name or name.endswith("/"):
        return None  # 目录条目
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part in ("..", "") for part in pure.parts if part != ""):
        return None  # 绝对路径 / 上跳 / 双斜杠
    if any(part in _JUNK_NAMES for part in pure.parts):
        return None
    normalized = str(pure)
    if any(normalized.startswith(p) for p in _JUNK_PREFIXES):
        return None
    return normalized


def _make_uploaded(name: str, content: bytes) -> File:
    """内存文件对象：保留相对路径名（UploadedFile.name 的 setter 会强制
    basename，子目录信息会被剥掉），同时提供与直传上传件同构的
    name/size/content_type/seek 接口，下游落盘协议零改动。"""
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    f = File(io.BytesIO(content), name=name)
    f.content_type = mime  # type: ignore[attr-defined]
    return f


def _reject(reason: str) -> None:
    raise ValidationException(
        f"压缩包无法展开：{reason}",
        code="ARCHIVE_EXTRACT_FAILED",
        errors={"files": reason},
    )


def _expand_zip(data: bytes, archive_name: str) -> list[File]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError) as exc:
        _reject(f"{archive_name} 不是有效的 zip 文件（{exc}）")
        return []  # pragma: no cover —— _reject 必抛

    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_ENTRIES:
        _reject(f"{archive_name} 内文件数超过上限（{len(infos)} > {MAX_ENTRIES}）")
    total = sum(i.file_size for i in infos)
    if total > MAX_TOTAL_BYTES:
        _reject(f"{archive_name} 展开后总量超过 {MAX_TOTAL_BYTES // (1024 * 1024)}MB 上限")
    for info in infos:
        if info.file_size > MAX_ENTRY_BYTES:
            _reject(f"{archive_name} 内 {info.filename} 超过单文件 50MB 上限")
        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESS_RATIO:
            _reject(f"{archive_name} 内 {info.filename} 压缩比异常（疑似 zip 炸弹）")

    results: list[File] = []
    skipped = 0
    for info in infos:
        safe = _sanitize_entry_name(info.filename)
        if safe is None:
            skipped += 1
            continue
        try:
            results.append(_make_uploaded(safe, zf.read(info)))
        except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
            _reject(f"{archive_name} 内 {info.filename} 读取失败（{exc}）")
    if skipped:
        logger.info("压缩包 %s 跳过 %d 个不安全/噪声条目", archive_name, skipped)
    return results


def _expand_with_bsdtar(data: bytes, archive_name: str) -> list[File]:
    """rar/7z 经 bsdtar（libarchive）解到临时目录后收集文件。"""
    binary = shutil.which("bsdtar") or shutil.which("tar")
    if binary is None:
        _reject(
            f"服务器未安装 bsdtar，无法解压 {Path(archive_name).suffix} 压缩包"
            "（zip 不受影响；请联系管理员安装 libarchive）"
        )
        return []  # pragma: no cover

    with tempfile.TemporaryDirectory(prefix="fachuan-archive-") as tmp:
        archive_path = Path(tmp) / "archive.bin"
        archive_path.write_bytes(data)
        try:
            # 二进制路径来自 which、参数固定，无 shell 注入面
            proc = subprocess.run(
                # 不用 -P：bsdtar 默认拒绝绝对路径/.. 条目；符号链接在收集阶段跳过
                [binary, "-xf", str(archive_path), "-C", tmp, "--no-same-owner"],
                capture_output=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            _reject(f"{archive_name} 解压超时（>120s）")
            return []  # pragma: no cover
        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()[:200]
            _reject(f"{archive_name} 解压失败：{stderr or '未知错误（可能是不支持的分卷/加密格式）'}")

        root = Path(tmp)
        # 只收普通文件：跳过符号链接（防链接跳出临时目录）与解出的目录结构本身
        files = sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink() and p != archive_path)
        if len(files) > MAX_ENTRIES:
            _reject(f"{archive_name} 内文件数超过上限（{len(files)} > {MAX_ENTRIES}）")
        total = sum(p.stat().st_size for p in files)
        if total > MAX_TOTAL_BYTES:
            _reject(f"{archive_name} 展开后总量超过 {MAX_TOTAL_BYTES // (1024 * 1024)}MB 上限")

        results: list[File] = []
        for path in files:
            if path.stat().st_size > MAX_ENTRY_BYTES:
                _reject(f"{archive_name} 内 {path.name} 超过单文件 50MB 上限")
            safe = _sanitize_entry_name(path.relative_to(root).as_posix())
            if safe is None:
                continue
            results.append(_make_uploaded(safe, path.read_bytes()))
        return results


def expand_upload_files(files: list[Any]) -> list[Any]:
    """把上传文件列表中的压缩包展开为包内文件（非压缩包原样保留）。

    展开后的内层文件复用 :func:`validate_manual_upload_file` 的白名单与
    大小校验（与直传完全同口径）；嵌套压缩包按普通附件保留不递归。
    全部展开后一个文件都没有（空压缩包）由调用方判定报错。
    """
    from apps.message_hub.services.manual_upload_service import validate_manual_upload_file

    expanded: list[Any] = []
    for uploaded in files:
        name = str(getattr(uploaded, "name", "") or "")
        if not is_archive_filename(name):
            expanded.append(uploaded)
            continue
        data = uploaded.read()
        uploaded.seek(0)
        if Path(name).suffix.lower() == ".zip":
            inner = _expand_zip(data, name)
        else:
            inner = _expand_with_bsdtar(data, name)
        for item in inner:
            validate_manual_upload_file(item)
        expanded.extend(inner)
        logger.info(
            "压缩包 %s 展开：%d 个文件进入材料包（嵌套压缩包按附件保留）",
            name,
            len(inner),
        )
    return expanded
