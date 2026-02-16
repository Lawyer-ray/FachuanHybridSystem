import json
import os
from pathlib import Path


def _snapshot_path() -> Path:
    return Path(__file__).parent / "snapshots" / "openapi_v1.json"


def test_openapi_v1_schema_snapshot():
    from apiSystem.api import api_v1

    schema = api_v1.get_openapi_schema()
    snapshot_path = _snapshot_path()
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    actual = json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n"
    update = (os.environ.get("UPDATE_SNAPSHOTS", "") or "").lower().strip() in ("true", "1", "yes")
    if update:
        snapshot_path.write_text(actual, encoding="utf-8")
        assert snapshot_path.exists()
        return
    if not snapshot_path.exists():
        raise AssertionError(
            f"缺少 OpenAPI 快照文件：{snapshot_path}。如需生成/更新，请运行：UPDATE_SNAPSHOTS=1 pytest -q --no-cov {Path(__file__).name}"
        )

    expected = snapshot_path.read_text(encoding="utf-8")
    assert actual == expected
