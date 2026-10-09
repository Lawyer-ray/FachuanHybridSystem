"""学习规则 JSON 数据文件路径。

安全审计（2026Q4）：学习规则原先以 Python 源码形式写入 ``_learned_rules.py``
再 ``importlib.reload`` 执行，构成"数据 → 可执行代码"注入面（管理员触发导出
即 RCE），且该 .py 被 git 跟踪，payload 可随 commit 分发。现改为 JSON 数据
文件，路径单独成模块便于 writer（learning_service）与 reader
（archive_classifier）共用，避免两侧各自拼接路径而漂移。
"""

from __future__ import annotations

from pathlib import Path

LEARNED_RULES_JSON_PATH: Path = Path(__file__).parent / "_learned_rules.json"
