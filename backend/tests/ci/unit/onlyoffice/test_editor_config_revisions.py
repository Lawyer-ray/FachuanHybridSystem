"""`build_editor_config` 的修订显示契约测试。

**为什么必须锁死**（真机血泪）：律师用 WPS/Word 打开同一份 docx 满是修订
（`w:ins`/`w:del`），OnlyOffice 画布却干干净净，看着像「AI 根本没改成」。
根因是 DS 的 `customization.review.reviewDisplay` **默认 `'original'`**
（官方 api.js 注释：`original for viewer, markup for editor`），即按「修订前的
原文」渲染，已有痕迹一律不画。

关键区分（别再混）：
- `trackChanges`  = 我现在敲字要不要留痕（**录制**开关）
- `reviewDisplay` = 文件里**已有**的痕迹要不要画出来（**回放**开关）

历史实现只给了 review 模式的 `trackChanges`，回放开关一个都没给，于是
「锁定修订」模式看着正常、其余模式全部隐藏修订。真机 A/B 实测：同一 docx，
去掉 reviewDisplay 则审阅面板不出现，给 markup 后「审查更改」面板立刻出现。

因此本测试对所有模式断言 `reviewDisplay == "markup"`——**view 模式也不例外**：
只读不等于可以隐瞒修订。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.onlyoffice.config import OnlyOfficeConfig
from apps.onlyoffice.services.signing import build_editor_config

CFG = OnlyOfficeConfig(
    docserver_url="http://ds.example:9980",
    internal_url="http://backend.example:8002",
    jwt_secret="unit-test-dummy-hs256-key-long-enough",  # pragma: allowlist secret
)


def _config(mode: str, file_name: str = "a.docx") -> dict[str, Any]:
    return build_editor_config(
        CFG,
        file_url_path="/api/v1/onlyoffice/file?src=%2Fapi%2Fv1%2Fx&sig=tok",
        file_name=file_name,
        document_key="key1",
        mode=mode,
        user_id="7",
        user_name="律师",
    )


class TestRevisionDisplay:
    @pytest.mark.parametrize("mode", ["view", "review", "edit"])
    def test_all_modes_show_existing_revisions(self, mode: str) -> None:
        """三种模式都必须回放已有修订痕迹（默认 original 的坑）。"""
        review = _config(mode)["editorConfig"]["customization"]["review"]
        assert review["reviewDisplay"] == "markup", f"{mode} 模式没开 markup，修订会看不见"

    @pytest.mark.parametrize("mode", ["view", "review", "edit"])
    def test_show_review_changes_on(self, mode: str) -> None:
        """审阅工具的修订视图开关默认展开，否则律师还得自己去找。"""
        review = _config(mode)["editorConfig"]["customization"]["review"]
        assert review["showReviewChanges"] is True

    def test_review_mode_still_records_track_changes(self) -> None:
        """修复不得回归掉 review 模式的「锁定修订」：录制开关必须还在。"""
        review = _config("review")["editorConfig"]["customization"]["review"]
        assert review["trackChanges"] is True

    def test_edit_mode_does_not_force_track_changes(self) -> None:
        """edit 是「律师直接改」，强制留痕会把他自己的正常编辑变成一堆修订。"""
        review = _config("edit")["editorConfig"]["customization"]["review"]
        assert "trackChanges" not in review

    def test_review_panel_does_not_leak_into_permissions(self) -> None:
        """回放开关只影响显示，不能顺手放开编辑权限（view 仍须只读）。"""
        cfg = _config("view")
        assert cfg["document"]["permissions"]["edit"] is False
        assert cfg["document"]["permissions"]["review"] is False

    def test_config_is_signed_after_review_block(self) -> None:
        """token 覆盖全部字段：加了 review 块必须是签名后产物（能被密钥解出）。"""
        import jwt as _jwt

        cfg = _config("edit")
        decoded = _jwt.decode(cfg["token"], CFG.jwt_secret, algorithms=["HS256"])
        assert decoded["editorConfig"]["customization"]["review"]["reviewDisplay"] == "markup"
