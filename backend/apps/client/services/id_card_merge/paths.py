"""Business logic services."""

from apps.core.config import get_config
from apps.core.path import Path


def get_media_root() -> Path:
    value = get_config("django.media_root", None)
    if not value:
        raise RuntimeError("MEDIA_ROOT 未配置")
    return Path(str(value))


def ensure_output_dir(media_root: Path) -> Path:
    output_dir = Path(str(media_root / "id_card_merged"))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def ensure_temp_dir(media_root: Path) -> Path:
    temp_dir = Path(str(media_root / "temp"))
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir
