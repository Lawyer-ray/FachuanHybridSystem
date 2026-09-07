"""S3-compatible storage provider (AWS S3, Cloudflare R2, MinIO, Backblaze B2, etc.)."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from .protocols import CloudFileInfo

logger = logging.getLogger(__name__)


class S3Provider:
    """Read/write files on S3-compatible object storage.

    Directories are simulated via key prefixes and trailing-slash marker objects.
    Uses ``boto3`` client directly for full control.
    """

    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        *,
        endpoint_url: str = "",
        region: str = "us-east-1",
        root_path: str = "",
    ) -> None:
        import boto3
        from botocore.config import Config

        self._bucket = bucket_name
        self._root = root_path.strip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "adaptive"}),
        )

    def _full_key(self, path: str) -> str:
        """Build S3 object key from a relative path."""
        clean = path.strip("/")
        parts = [p for p in (self._root, clean) if p]
        return "/".join(parts)

    # ── Protocol implementation ────────────────────────────────

    def list_directory(self, path: str) -> list[CloudFileInfo]:
        prefix = self._full_key(path)
        if prefix:
            prefix += "/"
        results: list[CloudFileInfo] = []

        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix, Delimiter="/"):
            # CommonPrefixes = "subdirectories"
            for cp in page.get("CommonPrefixes", []):
                dir_prefix = cp["Prefix"]
                name = dir_prefix[len(prefix) :].rstrip("/")
                if not name:
                    continue
                rel = f"{path.strip('/')}/{name}".lstrip("/")
                results.append(CloudFileInfo(name=name, path=rel, is_dir=True, size=0, modified_at=0.0))

            # Contents = files
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key == prefix.rstrip("/"):
                    continue
                name = key[len(prefix) :].rstrip("/")
                if not name or "/" in name:
                    continue
                rel = f"{path.strip('/')}/{name}".lstrip("/")
                results.append(
                    CloudFileInfo(
                        name=name,
                        path=rel,
                        is_dir=False,
                        size=obj.get("Size", 0),
                        modified_at=obj["LastModified"].timestamp(),
                    )
                )

        results.sort(key=lambda x: x.name.lower())
        return results

    def read_file(self, path: str) -> bytes:
        key = self._full_key(path)
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()  # type: ignore[no-any-return]

    def write_file(self, path: str, content: bytes) -> None:
        parent = "/".join(path.strip("/").split("/")[:-1])
        if parent:
            self.mkdir(parent)
        key = self._full_key(path)
        self._client.put_object(Bucket=self._bucket, Key=key, Body=content)

    def mkdir(self, path: str) -> None:
        parts = path.strip("/").split("/")
        for i in range(1, len(parts) + 1):
            sub = "/".join(parts[:i])
            if not self.exists(sub):
                key = self._full_key(sub) + "/"
                self._client.put_object(Bucket=self._bucket, Key=key, Body=b"")

    def exists(self, path: str) -> bool:
        key = self._full_key(path)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except self._client.exceptions.ClientError as e:
            error_code: str = e.response["Error"]["Code"]
            if error_code in ("404", "NoSuchKey"):
                # Fallback: check if any child objects exist under this prefix
                prefix = key + "/" if key else ""
                if prefix:
                    resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix, MaxKeys=1)
                    return bool(resp.get("KeyCount", 0) > 0)
                return False
            raise

    def is_dir(self, path: str) -> bool:
        prefix = self._full_key(path)
        if prefix:
            prefix += "/"
        resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix, MaxKeys=1)
        return bool(resp.get("KeyCount", 0) > 0)

    def delete_file(self, path: str) -> None:
        key = self._full_key(path)
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def get_file_info(self, path: str) -> CloudFileInfo | None:
        key = self._full_key(path)
        name = path.strip("/").split("/")[-1]
        # 1. 尝试作为文件
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=key)
            return CloudFileInfo(
                name=name,
                path=path.strip("/"),
                is_dir=False,
                size=resp.get("ContentLength", 0),
                modified_at=resp["LastModified"].timestamp(),
            )
        except self._client.exceptions.ClientError as e:
            error_code: str = e.response["Error"]["Code"]
            if error_code not in ("404", "NoSuchKey"):
                raise
        # 2. 尝试目录标记（trailing-slash key）
        try:
            resp = self._client.head_object(Bucket=self._bucket, Key=key + "/")
            return CloudFileInfo(
                name=name,
                path=path.strip("/"),
                is_dir=True,
                size=0,
                modified_at=resp["LastModified"].timestamp(),
            )
        except self._client.exceptions.ClientError:
            pass
        # 3. 虚拟目录（存在子对象）
        prefix = key + "/" if key else ""
        if prefix:
            resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix, MaxKeys=1)
            if resp.get("KeyCount", 0) > 0:
                return CloudFileInfo(name=name, path=path.strip("/"), is_dir=True, size=0, modified_at=0.0)
        return None

    def walk(self, path: str) -> Iterator[tuple[str, list[str], list[CloudFileInfo]]]:
        children = self.list_directory(path)
        subdirs = [c.name for c in children if c.is_dir]
        files = [c for c in children if not c.is_dir]
        yield (path, subdirs, files)
        for subdir in subdirs:
            sub_path = f"{path.rstrip('/')}/{subdir}"
            yield from self.walk(sub_path)
