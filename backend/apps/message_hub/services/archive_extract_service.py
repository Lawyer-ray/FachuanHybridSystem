"""上传压缩包展开 —— zip/rar/7z 拖进材料预处理台直接变成包内文件。

## 行为

```
材料.zip ─┐
合同.rar ─┼─ expand_upload_files() ─→ [a.pdf, b.jpg, 子目录/c.docx, ...]
发票.7z  ─┘      （压内文件逐个过同一套白名单/限额，展开后与逐个上传等价）
```

- **zip**：stdlib ``zipfile``（所有环境可用）。解压前先读 ``infolist`` 核对
  条目数/单条大小/总大小/压缩比（zip 炸弹防线）；**实际解压逐块流式复制**，
  不信任 infolist 谎报的大小（增量计数，超限即中止）。
- **rar / 7z**：``bsdtar``（libarchive）子进程解到临时目录后收集。二进制
  缺失时给明确错误而不是 500；具体格式支持面取决于系统 libarchive 构建。
- **加密压缩包**：识别 zipfile/bsdtar 的加密特征，明确提示「解密后再上传」。
- **分卷压缩包**（``.part1.rar`` / ``.z01`` / ``.zip.001`` 等）直接预检拒绝，
  提示先合并成完整压缩包。
- **安全**：
  - 路径穿越（zip slip）：条目名清洗为安全的 posix 相对路径，含 ``..``
    或绝对路径成分的条目**直接丢弃并计数**；
  - 容量：单条 ≤ 50MB（与直传单文件上限一致）、单包 ≤ 200 条 /
    200MB 未压缩总量、zip 压缩比 > 100 判为炸弹拒绝；
  - 白名单：展开后的内层文件走与直传完全相同的扩展名校验；
  - 嵌套压缩包**不递归**（内层 .zip/.rar/.7z 按普通压缩包附件保留，
    需要时用户可再拖一次）——防一层套一层的放大攻击。
- **噪声清理**：``__MACOSX/``、``.DS_Store``、``Thumbs.db``、
  ``desktop.ini`` 等 OS/压缩工具产物静默跳过。
- **内存**：全程流式——压缩包本体与展开产物都落 ``SpooledTemporaryFile``
  （小文件驻内存 8MB，超限自动滚磁盘），不再整包读进内存。
- **溯源**：展开产物带 ``expanded_from`` 属性（来源压缩包名），落库时写进
  附件 meta，前端可展示「来自 xxx.zip」。

展开产物提供与直传上传件同构的 name/size/content_type/seek 接口，
下游落盘/页数统计/追加协议零改动。
"""

from __future__ import annotations

import io
import logging
import mimetypes
import re
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
#: 流式复制块大小
_COPY_CHUNK = 1024 * 1024
#: 分卷压缩包命名（.part1.rar / .z01 / .zip.001 / .7z.002 / .rar.00x）
_MULTIPART_RE = re.compile(r"\.part\d+\.rar$|\.zip\.\d+$|\.7z\.\d+$|\.z\d+$|\.r\d+$|\.0\d+$", re.IGNORECASE)
#: SpooledTemporaryFile 驻内存上限（超过即滚磁盘）
_SPOOL_MEM_BYTES = 8 * 1024 * 1024

#: 系统/压缩工具噪声（不进材料包）
_JUNK_NAMES = {"__MACOSX", ".DS_Store", "Thumbs.db", "desktop.ini"}
_JUNK_PREFIXES = ("__MACOSX/",)

#: 加密特征（zipfile 的 RuntimeError / bsdtar 的 stderr）
_ZIP_ENCRYPTED_MARKERS = ("encrypted", "password required", "password")


def is_archive_filename(name: str) -> bool:
    return Path(name).suffix.lower() in ARCHIVE_EXTENSIONS


def is_multipart_filename(name: str) -> bool:
    """分卷压缩包命名（.part1.rar / .z01 / .zip.001 / .7z.002 / .r00 …）。"""
    return bool(_MULTIPART_RE.search(name))


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


class _ExtractedFile(File):
    """展开产物：显式 size（SpooledTemporaryFile 的 size 探测不可靠）+ 溯源。"""

    def __init__(
        self,
        file_obj: Any,
        name: str,
        size: int,
        content_type: str,
        expanded_from: str = "",
    ) -> None:
        self.file = file_obj
        self.name = name
        self._extracted_size = size
        self.content_type = content_type
        self.expanded_from = expanded_from

    @property
    def size(self) -> int:
        return self._extracted_size


def _make_uploaded(file_obj: Any, name: str, size: int, expanded_from: str = "") -> _ExtractedFile:
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    file_obj.seek(0)
    return _ExtractedFile(file_obj, name, size, mime, expanded_from)


def _reject(reason: str) -> None:
    raise ValidationException(
        f"压缩包无法展开：{reason}",
        code="ARCHIVE_EXTRACT_FAILED",
        errors={"files": reason},
    )


def _stream_copy(src: Any, dst: Any, *, limit_bytes: int, what: str) -> int:
    """逐块复制并增量计数；超过 limit 即中止（防 infolist 谎报的炸弹）。"""
    total = 0
    while True:
        chunk = src.read(_COPY_CHUNK)
        if not chunk:
            return total
        total += len(chunk)
        if total > limit_bytes:
            _reject(f"{what} 实际大小超过上限")
        dst.write(chunk)


def _copy_upload_to_temp(uploaded: Any, tmp_dir: Path) -> Path:
    """把上传的压缩包流式落到临时文件（zipfile/bsdtar 都需要可寻址输入）。"""
    tpath = tmp_dir / "archive.bin"
    size_cap = MAX_TOTAL_BYTES  # 压缩包本体理论上限（与展开总量同级）
    with tpath.open("wb") as dst:
        _stream_copy(uploaded, dst, limit_bytes=size_cap, what="压缩包本体")
    uploaded.seek(0)
    return tpath


def _expand_zip(tpath: Path, archive_name: str) -> list[_ExtractedFile]:
    try:
        zf = zipfile.ZipFile(tpath)
    except (zipfile.BadZipFile, OSError) as exc:
        _reject(f"{archive_name} 不是有效的 zip 文件（{exc}）")
        return []  # pragma: no cover —— _reject 必抛

    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_ENTRIES:
        _reject(f"{archive_name} 内文件数超过上限（{len(infos)} > {MAX_ENTRIES}）")
    declared_total = sum(i.file_size for i in infos)
    if declared_total > MAX_TOTAL_BYTES:
        _reject(f"{archive_name} 展开后总量超过 {MAX_TOTAL_BYTES // (1024 * 1024)}MB 上限")
    for info in infos:
        if info.file_size > MAX_ENTRY_BYTES:
            _reject(f"{archive_name} 内 {info.filename} 超过单文件 50MB 上限")
        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESS_RATIO:
            _reject(f"{archive_name} 内 {info.filename} 压缩比异常（疑似 zip 炸弹）")

    results: list[_ExtractedFile] = []
    skipped = 0
    actual_total = 0
    for info in infos:
        safe = _sanitize_entry_name(info.filename)
        if safe is None:
            skipped += 1
            continue
        spool: Any = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MEM_BYTES, prefix="fachuan-extract-")
        try:
            with zf.open(info) as src:
                # 限额 = 单条上限 与 剩余总量 中较小者（双保险，防谎报）
                room = min(MAX_ENTRY_BYTES, MAX_TOTAL_BYTES - actual_total)
                written = _stream_copy(src, spool, limit_bytes=room, what=f"{archive_name} 内 {info.filename}")
        except RuntimeError as exc:  # zipfile 对加密条目的标准异常
            spool.close()
            msg = str(exc)
            if any(marker in msg.lower() for marker in _ZIP_ENCRYPTED_MARKERS):
                _reject(f"{archive_name} 是加密压缩包，请解密后再上传（{info.filename} 需要密码）")
            _reject(f"{archive_name} 内 {info.filename} 读取失败（{msg}）")
            return []  # pragma: no cover
        except (zipfile.BadZipFile, OSError) as exc:
            spool.close()
            _reject(f"{archive_name} 内 {info.filename} 读取失败（{exc}）")
            return []  # pragma: no cover
        actual_total += written
        results.append(_make_uploaded(spool, safe, written, expanded_from=archive_name))
    if skipped:
        logger.info("压缩包 %s 跳过 %d 个不安全/噪声条目", archive_name, skipped)
    return results


def _expand_with_bsdtar(tpath: Path, archive_name: str, tmp_dir: Path) -> list[_ExtractedFile]:
    """rar/7z 经 bsdtar（libarchive）解到临时目录后收集文件。"""
    binary = shutil.which("bsdtar") or shutil.which("tar")
    if binary is None:
        _reject(
            f"服务器未安装 bsdtar，无法解压 {Path(archive_name).suffix} 压缩包"
            "（zip 不受影响；请联系管理员安装 libarchive）"
        )
        return []  # pragma: no cover

    extract_dir = tmp_dir / "out"
    extract_dir.mkdir()
    try:
        proc = subprocess.run(  # 二进制路径来自 which、参数固定，无 shell 注入面
            [binary, "-xf", str(tpath), "-C", str(extract_dir), "--no-same-owner"],
            capture_output=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _reject(f"{archive_name} 解压超时（>120s）")
        return []  # pragma: no cover
    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
        lowered = stderr.lower()
        if any(m in lowered for m in ("password", "encrypted", "passphrase")):
            _reject(f"{archive_name} 是加密压缩包，请解密后再上传")
        _reject(f"{archive_name} 解压失败：{stderr.strip()[:200] or '未知错误（可能是不支持的分卷/加密格式）'}")
        return []  # pragma: no cover

    root = extract_dir
    # 只收普通文件：跳过符号链接（防链接跳出临时目录）
    files = sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink())
    if len(files) > MAX_ENTRIES:
        _reject(f"{archive_name} 内文件数超过上限（{len(files)} > {MAX_ENTRIES}）")
    total = sum(p.stat().st_size for p in files)
    if total > MAX_TOTAL_BYTES:
        _reject(f"{archive_name} 展开后总量超过 {MAX_TOTAL_BYTES // (1024 * 1024)}MB 上限")

    results: list[_ExtractedFile] = []
    for path in files:
        if path.stat().st_size > MAX_ENTRY_BYTES:
            _reject(f"{archive_name} 内 {path.name} 超过单文件 50MB 上限")
        safe = _sanitize_entry_name(path.relative_to(root).as_posix())
        if safe is None:
            continue
        results.append(_make_uploaded(path.open("rb"), safe, path.stat().st_size, expanded_from=archive_name))
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
        if is_multipart_filename(name):
            _reject(f"{name} 是分卷压缩包，请先在本地合并成完整压缩包再上传")
        with tempfile.TemporaryDirectory(prefix="fachuan-archive-") as tmp:
            tpath = _copy_upload_to_temp(uploaded, Path(tmp))
            if Path(name).suffix.lower() == ".zip":
                inner = _expand_zip(tpath, name)
            else:
                inner = _expand_with_bsdtar(tpath, name, Path(tmp))
        for item in inner:
            validate_manual_upload_file(item)
        expanded.extend(inner)
        logger.info(
            "压缩包 %s 展开：%d 个文件进入材料包（嵌套压缩包按附件保留）",
            name,
            len(inner),
        )
    return expanded
