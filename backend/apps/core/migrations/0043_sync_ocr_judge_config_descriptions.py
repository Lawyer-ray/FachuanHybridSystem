"""同步多引擎分歧裁定两项配置的说明文案（去掉「尚未接线」那句过期话）。

起因：`OCR_JUDGE_ENABLED` 的说明是在 v27.25.4 写的，当时打分器只有组件、还没接进双引擎
主链，所以写着「且主链已接线（否则开关无效果）」，代码注释更直接写着「组件已实现但
**尚未接线到主链**，现在打开开关不会产生任何效果」。v27.25.6 之后
`dual_engine_runner.run_dual_engine` 已经把它接进主链（`judge_requested` /
`judge_effective`），这句就变成了**会误导运维的化石文案**：

- 读到「没接线」→ 干脆不打开，功能白做；
- 或打开了但以为没效果，将来分歧没被自动裁定就归因成「坏了」（实际可能是缺 key）。

## 为什么必须写成迁移，而不是只改 `_service_configs.py`

`SystemConfigAdmin.init_defaults_view` 用的是 `get_or_create(key=..., defaults=...)`：
**已存在的行一个字段都不会更新**。所以只改种子代码，本机 / 线上那份配置的说明一个字都
不会变，只有全新部署才看得到新文案——「改了代码却没生效」的典型形状。

## 覆盖范围收得很窄

只在**库里文案等于旧默认值（或为空）**时才覆盖。管理员手工改过的说明一律不动：
那是他的判断，迁移没有资格替他重写。

回滚：把同样两条按 key 反向写回旧文案（同样只在库里等于新文案时才动）。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import migrations
from django.db.models import Q

logger = logging.getLogger(__name__)

#: key → (旧默认说明, 新说明)。两条都是「因部署而异」的开关/密钥说明，不是文案美化：
#: 旧文案声称功能未接线（假），且没写「两级门禁」这个用户最需要知道的优先级。
_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "OCR_JUDGE_ENABLED": (
        "多引擎分歧是否用第三方打分器裁定（0=关，默认；1=开）。"
        "关着时与引入该功能前逐位一致：分歧只进人工抽屉。"
        "打开前需先填 OCR_JUDGE_API_KEY，且主链已接线（否则开关无效果）。",
        "多引擎分歧是否用第三方打分器自动裁定（0=关，默认；1=开）。"
        "这是**部署级总闸**：关着或缺 Key 时一条都不判，分歧全部进人工清单。"
        "与任务级开关（材料预处理 → 自动分段设置 → 分歧自动裁定）两级都过才生效；"
        "缺 Key 时按未启用处理，日志会有 ocr_judge_enabled_without_key 提示。",
    ),
    "OCR_JUDGE_API_KEY": (  # pragma: allowlist secret —— 这是配置键名，不是密钥本身
        "分歧裁定打分器的 API Key（Bearer Token）。留空则判定一律落人工；敏感项，加密存储。"
        "供应商侧政策：可读分辨率下的证件图像会被拒（content_policy_violation），"
        "所以证件/账号类字段不走此路，走 L1 校验位。",
        "分歧裁定打分器的 API Key（Bearer Token）。敏感项，加密存储。"
        "它只决定「这台环境**能不能**判」，不决定「这份卷宗**要不要**判」——后者在任务上。"
        "留空时即使总闸打开也按未启用处理，分歧全部落人工。"
        "供应商侧政策：可读分辨率下的证件图像会被拒（content_policy_violation），"
        "所以证件/账号类字段不走此路，走 L1 校验位。",
    ),
}


def _sync(apps: Any, schema_editor: Any, *, forward: bool) -> None:
    """按 key 改写说明：只动「库里仍是另一版默认文案」的那几行。"""
    SystemConfig = apps.get_model("core", "SystemConfig")
    for key, (old, new) in _DESCRIPTIONS.items():
        source, target = (old, new) if forward else (new, old)
        # 空说明也算「没被管理员改过」，一并补上：早期手工建的行同样需要这句真话。
        updated = (
            SystemConfig.objects.filter(key=key)
            .filter(Q(description=source) | Q(description=""))
            .update(description=target)
        )
        if updated:
            logger.info("已同步配置说明：%s（%d 行）", key, updated)


def forwards(apps: Any, schema_editor: Any) -> None:
    _sync(apps, schema_editor, forward=True)


def backwards(apps: Any, schema_editor: Any) -> None:
    _sync(apps, schema_editor, forward=False)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0042_restore_onlyoffice_category_and_purge_tts_configs"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
