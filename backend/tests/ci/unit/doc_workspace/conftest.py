"""文档工作面单测的公共夹具。

**为什么要把 MEDIA_ROOT 指到 tmp**：落笔与保存回写都会先拍快照，快照落
MEDIA_ROOT 下的 `doc_snapshots/`。默认 MEDIA_ROOT 是仓库里的
`apiSystem/media/`，不隔离就会在跑测试时污染开发机的媒体目录。
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
