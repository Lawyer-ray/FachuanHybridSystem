"""_RecursiveWalkMixin 单元测试：递归遍历的共享实现."""

from __future__ import annotations

from apps.cloud_storage.dropbox_provider import DropboxProvider
from apps.cloud_storage.onedrive_provider import OneDriveProvider
from apps.cloud_storage.protocols import CloudFileInfo
from apps.cloud_storage.providers_mixin import _RecursiveWalkMixin
from apps.cloud_storage.s3_provider import S3Provider
from apps.cloud_storage.webdav_provider import WebDAVProvider


def _info(name: str, path: str, *, is_dir: bool) -> CloudFileInfo:
    return CloudFileInfo(name=name, path=path, is_dir=is_dir, size=0 if is_dir else 1, modified_at=0.0)


class _FakeTreeProvider(_RecursiveWalkMixin):
    """以预置目录树实现 list_directory，用于验证 walk 的递归行为."""

    def __init__(self, tree: dict[str, list[CloudFileInfo]]) -> None:
        self._tree = tree
        self.list_calls: list[str] = []

    def list_directory(self, path: str) -> list[CloudFileInfo]:
        self.list_calls.append(path)
        return self._tree.get(path, [])


class TestRecursiveWalkMixin:
    def test_yields_each_directory_depth_first(self) -> None:
        provider = _FakeTreeProvider(
            {
                "/": [_info("a", "/a", is_dir=True), _info("x.txt", "/x.txt", is_dir=False)],
                "/a": [_info("b", "/a/b", is_dir=True)],
                "/a/b": [],
            }
        )
        results = list(provider.walk("/"))

        assert [dirpath for dirpath, _subdirs, _files in results] == ["/", "/a", "/a/b"]
        assert [subdirs for _dirpath, subdirs, _files in results] == [["a"], ["b"], []]
        assert [f.name for _dirpath, _subdirs, files in results for f in files] == ["x.txt"]

    def test_joins_sub_path_after_stripping_trailing_slash(self) -> None:
        provider = _FakeTreeProvider({"/root/": [_info("child", "/root/child", is_dir=True)], "/root/child": []})

        results = list(provider.walk("/root/"))

        assert provider.list_calls == ["/root/", "/root/child"]
        assert [dirpath for dirpath, _subdirs, _files in results] == ["/root/", "/root/child"]

    def test_empty_directory_yields_only_itself(self) -> None:
        provider = _FakeTreeProvider({"/empty": []})

        assert list(provider.walk("/empty")) == [("/empty", [], [])]

    def test_all_sync_providers_share_the_mixin(self) -> None:
        for cls in (S3Provider, WebDAVProvider, OneDriveProvider, DropboxProvider):
            assert issubclass(cls, _RecursiveWalkMixin)
            assert cls.walk is _RecursiveWalkMixin.walk
