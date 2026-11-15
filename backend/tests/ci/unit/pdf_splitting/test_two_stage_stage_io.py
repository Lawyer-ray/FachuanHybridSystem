"""``two_stage`` 阶段间产物读写的降级契约。

存在理由：这条链是**两个独立的 Django-Q 任务**，阶段之间只能靠任务目录里的文件
传递（``pages.json`` / ``page_quality.json`` / ``engine_disagreements.json``）。
文件是唯一的信道，所以"文件出问题时该怎么办"是设计决策，不是巧合：

* **读**一律回空表而不是抛：损坏的产物顶多让下游少一点附加信息（正文/坐标/
  质量提示/分歧摘要），绝不能让一个已经跑完 164 页的任务变成打不开；
* **写**（``save_engine_disagreements``）必须真的落盘：分歧是在取字阶段跟双引擎
  一起算出来的，不落盘就得在分段阶段重跑两个云端引擎——等于整本卷宗再付一次费。

``advance_after_extract`` 的推进分叉（双引擎 → cross_check / 否则 → segment）
已由 ``test_stage_chain.py`` 覆盖，这里不重复。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from apps.pdf_splitting.services.split import two_stage


def _storage(tmp_path: Path) -> Any:
    """构造只带分歧产物路径的 storage 替身（``write_json`` 真写盘）。"""
    storage = MagicMock()
    storage.engine_disagreements_json_path = tmp_path / "engine_disagreements.json"

    def write_json(path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    storage.write_json.side_effect = write_json
    return storage


class TestEngineDisagreementsRoundTrip:
    def test_落盘读回往返(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path)
        payload = {
            "engine_disagreements": [{"page_no": 3, "kind": "char", "severity": "high"}],
            "engine_disagree_summary": {"high": 1},
            "dual_engine": {"engines": {"mineru": {"ok": True}, "paddleocr_vl": {"ok": True}}},
        }

        two_stage.save_engine_disagreements(storage, payload)

        assert storage.engine_disagreements_json_path.exists(), "分歧必须真实落盘，否则分段阶段得重跑云端"
        assert two_stage.load_engine_disagreements(storage) == payload


class TestLoadEngineDisagreementsDegradation:
    """四类降级：文件不存在 / JSON 损坏 / 顶层不是 dict / 读文件 OSError。"""

    def test_文件不存在回空表(self, tmp_path: Path) -> None:
        """旧任务、以及没勾双引擎的任务都没有这个产物——不能因此报错。"""
        assert two_stage.load_engine_disagreements(_storage(tmp_path)) == {}

    def test_json损坏回空表(self, tmp_path: Path) -> None:
        """写一半被杀（磁盘满 / worker 超时）会留下半截 JSON。"""
        storage = _storage(tmp_path)
        storage.engine_disagreements_json_path.write_text('{"engine_disagreements": [', encoding="utf-8")

        assert two_stage.load_engine_disagreements(storage) == {}

    def test_顶层不是字典回空表(self, tmp_path: Path) -> None:
        """写成了数组时不能把它直接当 dict 用（下游是 ``payload.get(...)``）。"""
        storage = _storage(tmp_path)
        storage.engine_disagreements_json_path.write_text('[{"page_no": 1}]', encoding="utf-8")

        assert two_stage.load_engine_disagreements(storage) == {}

    def test_读文件OSError回空表(self, tmp_path: Path) -> None:
        """文件在但读不动（权限 / 被占用）也只能降级，不能拖垮任务详情接口。"""
        from unittest.mock import patch

        storage = _storage(tmp_path)
        storage.engine_disagreements_json_path.write_text("{}", encoding="utf-8")

        with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
            assert two_stage.load_engine_disagreements(storage) == {}
