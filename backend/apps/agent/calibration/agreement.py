"""跨 judge 的一致性统计：换序两方向的合流与位置一致性。

## 为什么 tie 要单独算一类

每条 rubric 的判定都跑两个方向（换序）。两方向一致才算"一个判定"，不一致就是 tie：

* 计一致率与 kappa 时 tie **既不进分子也不进分母**（FastChat ``show_result.py:64-66``
  的二元门禁口径：宁可少判，不许硬裁——把两个方向里随便哪个当成真值，等于让"候选
  排在第几个"决定结论）；
* 计位置一致性时 tie **必须留在分母里**——那正是位置偏差的信号，先剔掉它再报
  "位置很稳"，等于把要报的问题删掉再宣布没问题。

两处口径不同，所以"过滤 tie"只发生在调用方（``metrics.compute_metrics``），
本模块的两个函数各自面对完整集合，谁都不替谁做过滤。
"""

from __future__ import annotations

from collections.abc import Sequence

#: 一次换序判定：``(方向 1 判"有缺陷", 方向 2 判"有缺陷")``。
Direction = tuple[bool, bool]


def merge_directions(direction: Direction) -> bool | None:
    """两方向合流：一致取该值，不一致返回 ``None``（tie，交人工）。"""
    forward, reverse = direction
    return forward if forward == reverse else None


def position_consistency(directions: Sequence[Direction]) -> float | None:
    """换序两方向同向的比例 = ``#(g1 ≡ g2) / N``（口径见 07-calibration.md F.2 第 5 条）。

    这是最便宜的位置偏差哨兵：它掉下来通常早于一致率，因为"两个方向自己先打架"
    是 prompt 不稳或位置偏差的直接症状。空输入返回 ``None``，不返回 0。
    """
    total = len(directions)
    if not total:
        return None
    consistent = sum(1 for forward, reverse in directions if forward == reverse)
    return consistent / total
