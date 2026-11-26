"""OnlyOffice 单测的公共夹具。

**为什么要把 MEDIA_ROOT 指到 tmp**：保存回写会在覆盖前拍一份文档快照
（`apps/doc_workspace.services.snapshot_service`），而 MEDIA_ROOT 默认指向
仓库里的 `apiSystem/media/`。不隔离的话，跑一次单测就会往开发机的媒体目录
里塞一堆 `doc_snapshots/*.docx`，既脏又会让「媒体目录里有什么」变得不可信。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from django.test import override_settings


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path: Path) -> Iterator[None]:
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        yield
