"""Business logic services."""

from django.conf import settings

from apps.core.config import get_config
from pathlib import Path


def get_media_root() -> Path:
    media_root = getattr(settings, "MEDIA_ROOT", None)
    if not media_root:
        media_root = get_config("django.media_root", None)
    if not media_root:
        raise RuntimeError("MEDIA_ROOT 未配置")
    return Path(str(media_root))


def ensure_output_dir(media_root: Path) -> Path:
    output_dir = media_root / "id_card_merged"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def ensure_temp_dir(media_root: Path) -> Path:
    temp_dir = media_root / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir
