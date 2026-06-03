"""Cloud storage folder scanner — adapts CloudStorageProvider to BoundFolderScanService interface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from apps.core.cloud_storage.protocols import CloudFileInfo, CloudStorageProvider


@dataclass(frozen=True)
class ScannedFile:
    """Lightweight wrapper that mirrors Path properties used by BoundFolderScanService."""

    _info: CloudFileInfo
    _root: str

    @property
    def name(self) -> str:
        return self._info.name

    @property
    def stem(self) -> str:
        return PurePosixPath(self._info.name).stem

    @property
    def suffix(self) -> str:
        return PurePosixPath(self._info.name).suffix

    @property
    def as_posix(self) -> str:  # type: ignore[override]
        return self._info.path

    @property
    def stat(self) -> _FakeStat:  # type: ignore[override]
        return _FakeStat(size=self._info.size, mtime=self._info.modified_at)

    def relative_to(self, other: str) -> PurePosixPath:
        return PurePosixPath(self._info.path).relative_to(other)

    @property
    def parent(self) -> _FakeParent:
        return _FakeParent(path=self._info.path)


@dataclass(frozen=True)
class _FakeStat:
    size: int
    mtime: float


class _FakeParent:
    def __init__(self, path: str) -> None:
        self._path = path

    @property
    def name(self) -> str:
        return PurePosixPath(self._path).parent.name

    def relative_to(self, other: str) -> PurePosixPath:
        parent_posix = str(PurePosixPath(self._path).parent)
        return PurePosixPath(parent_posix).relative_to(other)


class CloudFolderScanner:
    """Collects PDF files from a CloudStorageProvider, matching the interface BoundFolderScanService expects."""

    def __init__(self, provider: CloudStorageProvider, root_path: str) -> None:
        self._provider = provider
        self._root = root_path.rstrip("/")

    def collect_pdf_files(self) -> list[ScannedFile]:
        """Recursively collect all PDF files from the bound folder."""
        results: list[ScannedFile] = []
        for dirpath, _subdirs, files in self._provider.walk(self._root):
            for f in files:
                if f.name.lower().endswith(".pdf"):
                    # Build full relative path from scan root
                    if dirpath == self._root:
                        rel_path = f.name
                    else:
                        rel_path = dirpath[len(self._root) :].lstrip("/") + "/" + f.name
                    full_info = CloudFileInfo(
                        name=f.name,
                        path=rel_path,
                        is_dir=f.is_dir,
                        size=f.size,
                        modified_at=f.modified_at,
                    )
                    results.append(ScannedFile(_info=full_info, _root=self._root))
        results.sort(key=lambda x: x.as_posix)
        return results

    def read_file_bytes(self, scanned: ScannedFile) -> bytes:
        """Read file content from cloud storage."""
        return self._provider.read_file(scanned._info.path)
