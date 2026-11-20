"""与律师标注的一致性指标：raw 一致率 / Cohen kappa / PABAK / 子类 recall。

纯函数、无 Django、无网络、无随机（本包整体不 import 任何 Django，见 ``__init__.py``）。

## 输入数据形状（``--data`` 读的 JSON；``--dry-run`` 用同构的合成样本）

```json
{
  "rubric_id": "<str>", "rubric_version": "<str>",
  "families_agreeing": "<int：该轮判定里同向的 judge 家族数>",
  "margin": "<float：胜出候选对第二名的差距，不是本模块算出来的>",
  "samples": [
    {"contract_id": "<str>", "items": [
      {"rubric_id": "<str>", "defect_class": "miss | over | cite", "lawyer_defect": "<bool：律师仲裁后确有缺陷>",
       "judge_defect_forward": "<bool：换序方向 1 判有缺陷>", "judge_defect_reverse": "<bool：方向 2>"}
    ]}
  ]
}
```

一个 ``item`` = 一份合同 × 一条 rubric 的**二元判定单元**；``defect_class`` 的键与 A3
rubric 的 tags（``miss`` / ``over`` / ``cite``）同口径。``families_agreeing`` 与 ``margin``
是**判定运行侧记录的观测量**，不是从 item 推出来的：脚本自己去猜这两个数，等于自己给
自己发门禁，所以它们必须随数据给出，缺了就报错。

## 两条建模决定

1. **统一成"缺陷是否存在"**：rubric 的正负极性不能让 item 自己声明（正分项"满足"是好
   事，负分项"满足"是坏事），所以三个子类的 recall 用同一个正类——该项是否存在缺陷。
   这样"漏改"的 FN（应改未改却判合规）与"引用失效"的 FN 才是同一种错误。
2. **"没测到"一律 ``None``**：空输入若折算成 ``0``，报告就写着"一致率 0"，读的人分不清
   "完全不一致"与"根本没数据"，而 0 还会作为真实低分进 Stage 门禁。同理子类无标注时
   recall 是 ``None``；kappa 的分母 ``1 - pe`` 退化为 0（双方判定塌成同一个常数）时也是
   ``None``——那种样本上 kappa 数学上无定义，硬算出 0 只会误导。
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .agreement import Direction, merge_directions, position_consistency

#: 缺陷子类 → 中文名。键与 A3 rubric 的 tags 同口径；插入顺序即报告里的呈现顺序。
DEFECT_CLASSES: dict[str, str] = {"miss": "漏改", "over": "越界", "cite": "引用失效"}

#: 浮点容差。只用于"分母是否退化为 0"，不用来判阈值是否达标（那是 ``stage.py`` 的事）。
_EPS = 1e-12

#: JSON 顶层必填字段。少一个就报错，不给默认值：默认值会让"没记录"看起来像"记录为 0"。
_REQUIRED_FIELDS = ("rubric_id", "rubric_version", "families_agreeing", "margin", "samples")


class CalibrationDataError(ValueError):
    """校准数据文件不存在或不合规。消息必须写清"哪个文件、哪个字段"。"""


@dataclass(frozen=True)
class JudgmentUnit:
    """一份合同 × 一条 rubric 的一次判定，含换序两方向。"""

    rubric_id: str
    #: 取值见 ``DEFECT_CLASSES``；拼错名字会让该子类"没有样本"，所以构造时就报错。
    defect_class: str
    lawyer_defect: bool
    judge_defect_forward: bool
    judge_defect_reverse: bool

    def __post_init__(self) -> None:
        if self.defect_class not in DEFECT_CLASSES:
            raise ValueError(f"defect_class 必须是 {tuple(DEFECT_CLASSES)} 之一，实际是 {self.defect_class!r}")

    @property
    def direction(self) -> Direction:
        """换序两方向，交给 ``agreement`` 层的纯函数。"""
        return (self.judge_defect_forward, self.judge_defect_reverse)


@dataclass(frozen=True)
class CalibrationSample:
    """一份合同的全部判定单元。"""

    contract_id: str
    items: tuple[JudgmentUnit, ...]


@dataclass(frozen=True)
class CalibrationPayload:
    """一份校准数据的全部入参（含判定运行侧记录的 family 数与 margin）。"""

    rubric_id: str
    rubric_version: str
    families_agreeing: int
    margin: float
    samples: tuple[CalibrationSample, ...]


@dataclass(frozen=True)
class RecallStat:
    """一个缺陷子类的 recall 明细。

    ``gold_positives == 0`` 时 ``recall`` 是 ``None``：该子类这批样本里一条都没标，
    报 0 等于说"judge 一条都没抓到"，而事实是"没测"。
    """

    defect_class: str
    label: str
    gold_positives: int
    hits: int
    recall: float | None


@dataclass(frozen=True)
class CalibrationMetrics:
    """一次校准的全部指标。所有"没测到"的字段都是 ``None``。"""

    contracts: int
    units: int
    #: 换序两方向不一致的单元（tie），不进一致率 / kappa 的分母。
    tied_units: int
    scored_units: int
    #: 以下两个计数只统计 ``scored_units`` 内的单元。
    lawyer_defect_units: int
    judge_defect_units: int
    raw_agreement: float | None
    kappa: float | None
    pabak: float | None
    subclass_recalls: tuple[RecallStat, ...]
    position_consistency: float | None

    def recall_for(self, defect_class: str) -> float | None:
        """取某个子类的 recall。

        名字拼错时**报错而不是返回 None**：返回 None 会被 Stage 判定读成"没数据"，
        与"这个子类真的没测出来"混成一样，是查不出来的静默缺陷。
        """
        for stat in self.subclass_recalls:
            if stat.defect_class == defect_class:
                return stat.recall
        raise KeyError(f"未知缺陷子类 {defect_class!r}，可选：{tuple(DEFECT_CLASSES)}")


def load_payload(path: Path) -> CalibrationPayload:
    """读真实校准数据。文件不存在 / JSON 坏掉 / schema 不合规一律抛 ``CalibrationDataError``。

    这里**没有任何回退**：读不到就报错退出，绝不悄悄换成合成样本——否则"没跑过"
    会显示成"跑过了"。真实数据本批不提供，需要判定运行侧先产出。
    """
    if not path.is_file():
        raise CalibrationDataError(
            f"找不到校准数据文件：{path}。本批不提供真实数据；"
            f"--data 需要判定运行侧先产出该文件（JSON 形状见 metrics.py 模块 docstring）"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CalibrationDataError(f"{path} 不是合法 JSON：{exc}") from exc
    return parse_payload(raw, source=str(path))


def parse_payload(raw: object, *, source: str = "<memory>") -> CalibrationPayload:
    """把已解析的 JSON 对象校验成 ``CalibrationPayload``。``source`` 只用于错误消息。"""
    if not isinstance(raw, dict):
        raise CalibrationDataError(f"{source}：顶层必须是 JSON 对象")
    missing = [field for field in _REQUIRED_FIELDS if field not in raw]
    if missing:
        raise CalibrationDataError(f"{source}：缺少字段 {', '.join(missing)}")

    samples_raw = raw["samples"]
    if not isinstance(samples_raw, list):
        raise CalibrationDataError(f"{source}：samples 必须是数组")
    samples = tuple(_parse_sample(item, f"{source} samples[{index}]") for index, item in enumerate(samples_raw))

    contract_ids = [sample.contract_id for sample in samples]
    duplicated = sorted({contract_id for contract_id in contract_ids if contract_ids.count(contract_id) > 1})
    if duplicated:
        raise CalibrationDataError(f"{source}：contract_id 重复 {', '.join(duplicated)}（重复会让样本量虚高）")

    return CalibrationPayload(
        rubric_id=_require_text(raw["rubric_id"], "rubric_id", source),
        rubric_version=_require_text(raw["rubric_version"], "rubric_version", source),
        families_agreeing=_require_count(raw["families_agreeing"], "families_agreeing", source),
        margin=_require_finite(raw["margin"], "margin", source),
        samples=samples,
    )


def compute_metrics(payload: CalibrationPayload) -> CalibrationMetrics:
    """算一次校准的全部指标。空输入 → 所有比例字段 ``None``，计数为 0。"""
    units = tuple(unit for sample in payload.samples for unit in sample.items)
    scored = _scored_units(units)
    pairs = tuple((unit.lawyer_defect, merged) for unit, merged in scored)
    raw = raw_agreement(pairs)
    return CalibrationMetrics(
        contracts=len(payload.samples),
        units=len(units),
        tied_units=len(units) - len(scored),
        scored_units=len(scored),
        lawyer_defect_units=sum(1 for gold, _ in pairs if gold),
        judge_defect_units=sum(1 for _, pred in pairs if pred),
        raw_agreement=raw,
        kappa=cohen_kappa(pairs),
        pabak=pabak(raw),
        subclass_recalls=subclass_recalls(units),
        position_consistency=position_consistency(tuple(unit.direction for unit in units)),
    )


def raw_agreement(pairs: Sequence[tuple[bool, bool]]) -> float | None:
    """``(律师, judge)`` 配对里同判的比例；没有配对就是 ``None``。"""
    total = len(pairs)
    if not total:
        return None
    return sum(1 for gold, pred in pairs if gold == pred) / total


def cohen_kappa(pairs: Sequence[tuple[bool, bool]]) -> float | None:
    """Cohen's kappa：``(po - pe) / (1 - pe)``。

    ``1 - pe`` 退化为 0（双方判定都是同一个常数）时返回 ``None``：那种样本上 kappa
    没有定义，而公式会给出 0/0。用容差判零，不用 ``==`` 判浮点。
    """
    total = len(pairs)
    if not total:
        return None
    observed = sum(1 for gold, pred in pairs if gold == pred) / total
    gold_positives = sum(1 for gold, _ in pairs if gold)
    pred_positives = sum(1 for _, pred in pairs if pred)
    gold_negatives = total - gold_positives
    pred_negatives = total - pred_positives
    expected = (gold_positives * pred_positives + gold_negatives * pred_negatives) / (total * total)
    denominator = 1.0 - expected
    if math.isclose(denominator, 0.0, abs_tol=_EPS):
        return None
    return (observed - expected) / denominator


def pabak(agreement: float | None) -> float | None:
    """PABAK = ``2 * po - 1``：分布极偏时 kappa 会"高一致率低 kappa"，本指标作对照。

    ``None`` 与 NaN 都返回 ``None``：NaN 一旦漏进报告，任何阈值比较都会判 False，
    门禁看起来像"就是没达标"，把"根本没算出来"藏起来。
    """
    if agreement is None or not math.isfinite(agreement):
        return None
    return 2.0 * agreement - 1.0


def subclass_recalls(units: Sequence[JudgmentUnit]) -> tuple[RecallStat, ...]:
    """三个子类各自的 recall = 命中 / 律师标注该子类有缺陷的单元数。

    tie 单元（换序两方向不一致）既不算命中也不算漏——口径见 ``agreement`` 模块。
    """
    # 先按子类计数，再拼三个子类：一遍扫完，避免每个子类各自重算一次合流结果。
    scored = _scored_units(units)
    positives = Counter(unit.defect_class for unit, _ in scored if unit.lawyer_defect)
    hits = Counter(unit.defect_class for unit, merged in scored if unit.lawyer_defect and merged)
    stats: list[RecallStat] = []
    for name, label in DEFECT_CLASSES.items():
        n_pos, n_hit = positives[name], hits[name]
        stats.append(
            RecallStat(defect_class=name, label=label, gold_positives=n_pos, hits=n_hit, recall=_ratio(n_hit, n_pos))
        )
    return tuple(stats)


def _scored_units(units: Sequence[JudgmentUnit]) -> tuple[tuple[JudgmentUnit, bool], ...]:
    """把非 tie 单元连同"合流后的 judge 判定"一起返回；tie 单元在这里被剔除。"""
    scored: list[tuple[JudgmentUnit, bool]] = []
    for unit in units:
        merged = merge_directions(unit.direction)
        if merged is None:
            continue
        scored.append((unit, merged))
    return tuple(scored)


def _ratio(numerator: int, denominator: int) -> float | None:
    """分母为 0 时返回 ``None``（"没测到"≠0）。"""
    if not denominator:
        return None
    return numerator / denominator


def _parse_sample(raw: object, where: str) -> CalibrationSample:
    if not isinstance(raw, dict):
        raise CalibrationDataError(f"{where}：必须是 JSON 对象")
    items_raw = raw.get("items")
    if not isinstance(items_raw, list):
        raise CalibrationDataError(f"{where}：items 必须是数组")
    return CalibrationSample(
        contract_id=_require_text(raw.get("contract_id"), "contract_id", where),
        items=tuple(_parse_unit(item, f"{where} items[{index}]") for index, item in enumerate(items_raw)),
    )


def _parse_unit(raw: object, where: str) -> JudgmentUnit:
    if not isinstance(raw, dict):
        raise CalibrationDataError(f"{where}：必须是 JSON 对象")
    try:
        return JudgmentUnit(
            rubric_id=_require_text(raw.get("rubric_id"), "rubric_id", where),
            defect_class=_require_text(raw.get("defect_class"), "defect_class", where),
            lawyer_defect=_require_bool(raw.get("lawyer_defect"), "lawyer_defect", where),
            judge_defect_forward=_require_bool(raw.get("judge_defect_forward"), "judge_defect_forward", where),
            judge_defect_reverse=_require_bool(raw.get("judge_defect_reverse"), "judge_defect_reverse", where),
        )
    except ValueError as exc:  # defect_class 不在 DEFECT_CLASSES 里
        raise CalibrationDataError(f"{where}：{exc}") from exc


def _require_text(value: object, field: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalibrationDataError(f"{where}：{field} 必须是非空字符串，实际是 {value!r}")
    return value.strip()


def _require_bool(value: object, field: str, where: str) -> bool:
    if not isinstance(value, bool):
        raise CalibrationDataError(f"{where}：{field} 必须是 true/false，实际是 {value!r}")
    return value


def _require_count(value: object, field: str, where: str) -> int:
    # bool 是 int 的子类，True 会被当成 1 混过类型检查，所以先排掉。
    if isinstance(value, bool) or not isinstance(value, int):
        raise CalibrationDataError(f"{where}：{field} 必须是整数，实际是 {value!r}")
    if value < 0:
        raise CalibrationDataError(f"{where}：{field} 不能为负，实际是 {value!r}")
    return value


def _require_finite(value: object, field: str, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalibrationDataError(f"{where}：{field} 必须是数字，实际是 {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise CalibrationDataError(f"{where}：{field} 必须是有限数，实际是 {value!r}（NaN/inf 会让门禁判成假绿）")
    return number
