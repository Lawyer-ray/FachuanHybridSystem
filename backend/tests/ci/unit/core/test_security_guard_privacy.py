"""`devtools/security_guard.py` 隐私正则的回归测试。

## 为什么单独给这个脚本写测试

它是 pre-commit 与 `backend-security-guard`（PR 必需检查）的共同实现，
**既不能漏报**（漏报真实住址 / 真实案名 = 隐私进公开仓库），**也不能误报**
（误报会把整个仓库存量的历史文案全拦下，逼开发者 `--no-verify` 绕过，
等于门禁失效）。

本文件的样本分两组：`MUST_FLAG`（必须拦）与 `MUST_PASS`（必须放行）。
两组都要保住——只调一边很容易把另一边调坏。
"""

from __future__ import annotations

import pytest

from devtools import security_guard as sg


def _hit(text: str) -> str | None:
    return sg._privacy_hit(text)


# ── 必须拦：真实隐私 ────────────────────────────────────────────────
MUST_FLAG = [
    # 案名：真实姓名（不在 ANON_NAME_PATTERN 白名单里），被「」/ 句首包住
    "本案系「刘建军诉周文涛民间借贷纠纷」一审",  # privacy-allow 虚构测试样本
    "2024 年「赵明辉与孙丽萍离婚纠纷」判决书",  # privacy-allow 虚构测试样本
    "刘建军诉周文涛民间借贷纠纷",  # privacy-allow 虚构测试样本
    # 案名：公司当事人
    "原告广州市南方建材有限公司诉佛山鹏程机械有限公司买卖合同纠纷",  # privacy-allow 虚构测试样本
    "深圳市华强贸易有限公司与佛山市南方物流有限公司运输合同纠纷",  # privacy-allow 虚构测试样本
    # 地址：门牌级（省市区 + 路 + 门牌号）
    "被告住所地：广东省佛山市南海区桂城街道南海大道 88 号 3 栋 501 室",  # privacy-allow 虚构测试样本
    "送达地址：广东省广州市天河区天河路 100 号",  # privacy-allow 虚构测试样本
    "户籍地：广东省佛山市南海区某某路3号",  # privacy-allow 虚构测试样本
    # 其他类型，确认改动没有连带破坏
    "联系手机 13812345678",  # privacy-allow 虚构测试样本
]

# ── 必须放行：此前被误拦的存量文案 ──────────────────────────────────
MUST_PASS = [
    # 「非诉」是否定说法（非诉业务 / 非诉线），不是「X诉Y」案名。
    # 这条是 v27.13.14 修的真问题：新注释被切成原告=三个非 / 被告=场景各配一组可
    " * 三个非诉场景各配一组可执行动作：",
    "非诉线工作台：委托 → 尽调 → 交付",
    "三个非诉场景各配一组可执行动作，覆盖专项 / 跨境 / 常年",
    "「三个非诉场景各配一组可执行动作」",
    # 「诉」后面是程序名词，不是当事人
    "诉前保全申请由本院管辖",
    # 「与」是构词成分
    "积极参与社会治理与诉源治理",
    # 「与执行…」是介词短语
    "对被执行人财产执行不当，可提出执行异议",
    "行政复议与执行异议之诉",
    # 到省市区为止是公开行政区划，不是隐私
    "合同签订地：广东省佛山市南海区。",
    "管辖法院：广东省佛山市南海区人民法院",
    "覆盖广东省佛山市南海区、广东省广州市天河区等多个辖区",
    # 已脱敏：既有白名单（某 / 张三李四等通用示例名）必须继续放行
    "本案系「张某诉某公司民间借贷纠纷」一审",
    "「李某与某某贸易有限公司买卖合同纠纷」",
    "「张三诉李四民间借贷纠纷」",
]


@pytest.mark.parametrize("text", MUST_FLAG)
def test_real_privacy_is_blocked(text: str) -> None:
    """真实住址 / 真实案名必须拦下——漏报等于隐私进公开仓库。"""
    assert _hit(text), f"应拦未拦：{text!r}"


@pytest.mark.parametrize("text", MUST_PASS)
def test_false_positive_does_not_block(text: str) -> None:
    """存量正常文案必须放行——误拦会逼开发者绕过门禁，门禁等于失效。"""
    assert _hit(text) is None, f"误拦：{text!r} → {_hit(text)!r}"


def test_address_requires_door_number() -> None:
    """地址门槛是「门牌级」：只到省市区 / 街道不算隐私，到门牌才算。

    正则口径必须与 LLM 复审提示词同口径，否则同一段文本正则拦、大模型放行，
    两边结论打架，开发者不知道该信哪个。
    """
    assert _hit("广东省佛山市南海区") is None
    assert _hit("广东省佛山市南海区桂城街道") is None
    # 门牌之间通常有空格（「南海大道 88 号」），字符类不放行 \\s 会整条断掉
    assert _hit("广东省佛山市南海区南海大道 88 号") is not None  # privacy-allow 虚构测试样本


def test_case_name_trimmed_to_nearest_delimiter() -> None:
    """贪婪前缀要被切掉：「本案系「X诉Y」」的原告是 X，不是「本案系「X」。

    切不切得干净不影响是否命中，但影响报错信息能不能让开发者一眼看懂
    （提示里要给出正确的当事人名，否则无从改起）。
    """
    hit = _hit("本案系「刘建军诉周文涛民间借贷纠纷」一审")  # privacy-allow 虚构测试样本
    assert hit is not None
    assert "刘建军" in hit
    assert "本案系" not in hit
