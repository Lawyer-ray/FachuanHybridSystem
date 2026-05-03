"""媒体路径工具。"""

from pathlib import Path

from django.utils.translation import gettext_lazy as _

from apps.core.services.storage_service import _get_media_root


def get_media_root() -> Path:
    media_root = _get_media_root()
    if not media_root:
        raise RuntimeError(_("MEDIA_ROOT 未配置"))
    return Path(media_root)


def ensure_output_dir(media_root: Path) -> Path:
    output_dir = media_root / "id_card_merged"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def ensure_temp_dir(media_root: Path) -> Path:
    temp_dir = media_root / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir
