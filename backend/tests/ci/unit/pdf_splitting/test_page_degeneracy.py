"""页级取字退化检测：判据边界 + 三条曾踩过的误判回归。

判据来自三份真实扫描卷宗（37 / 93 / 164 页）的校准，所以这里的用例分两类：

- **必须抓到**：复读循环、空返回、整页只有一张图。
- **必须不抓**：高密度表格页、只被截断但内容不重复的页、短行高频的表格页。
  后三条每一条都对应一次真实误判（>5000 字规则在 164 页银行流水上把 4 页正常交易明细
  全判成坏，由此得出「退化率 42%」的错误结论）。
"""

from __future__ import annotations

from apps.pdf_splitting.services.split.page_degeneracy import (
    degeneracy_reason,
    has_usable_text,
    is_degenerate,
    strip_cloud_markers,
)

#: 真实云端返回的「整页就是一张图」形态（`rich_layout_recognition`）。
#: 分隔符是全角竖线 U+FF5C，不是 ASCII `|`——按半角写正则会一条都匹配不到。
IMAGE_ONLY_MARKER = "<｜ref｜>image\uff5c[[213,0,999,999]]\uff5c>"

#: 一段真实正文（授权委托书）。
REAL_BODY = (
    "委托人：某某市某某物业管理有限公司，法定代表人：某某某，"
    "统一社会信用代码：91330100MA2XXXXXXX，住所地：某市民众镇某路段某路口对面。\n"
    "受托人：某某某 职务：律师\n"
    "工作单位：北京某（广州）律师事务所 联系电话：138****1234\n"
    "现委托某某某在委托人与国家税务总局某市税务局某税务分局税务行政诉讼案中，"
    "作为我方参与行政诉讼一审程序的委托代理人。"
)


class TestDegenerateDetected:
    def test_复读循环_同一行重复到上限(self) -> None:
        looped = "\n".join(["姓名 某某某\n性别 女\n出生 1976.6.29日"] * 200)
        assert "重复" in degeneracy_reason(looped, "length")

    def test_空返回_即使finish是stop也算坏(self) -> None:
        # 164 页银行档案首跑实测：11 页 finish_reason=stop 但正文是空串
        assert degeneracy_reason("", "stop") == "空返回"
        assert degeneracy_reason("   \n\t\n ", "stop") == "空返回"

    def test_整页只有一张图_没有正文(self) -> None:
        # 617 的 EMS 面单：云端自报「这一页就是一张图」。有字（是标记）但没有正文，
        # 曾经因为「剥标签后残留 image 这个词」被误判成有正文，漏掉修补。
        assert degeneracy_reason(IMAGE_ONLY_MARKER, "stop") == "只有标记没有正文"
        assert has_usable_text(IMAGE_ONLY_MARKER) is False

    def test_整页只有一行且行内反复吐同一句话(self) -> None:
        """617 的 p8 就是这个形态：13653 字只有 1 行，行重复与唯一行比例双双失效。"""
        body = "这是同一段话，被模型反复吐出来。" * 500
        assert "重复" in degeneracy_reason(body, "length")
        assert "\n" not in body, "用例本身要保证是单行"

    def test_被截断且内容重复(self) -> None:
        """多行短周期循环：行重复判据会先命中（这是预期路径，不是漏判）。"""
        body = "\n".join([f"第{i}行内容不同，但整段在循环" for i in range(6)] * 20)
        assert "同一行重复" in degeneracy_reason(body, "length")

    def test_只截断不重复的多行正文判OK(self) -> None:
        body = "\n".join(f"第{i}条：完全不同的第{i}项内容，写在合同第{i}条" for i in range(60))
        assert degeneracy_reason(body, "length") == ""


class TestMustNotFalsePositive:
    def test_高密度表格页不算坏_字数不是证据(self) -> None:
        """回归：曾经用 len(text) > 5000 当判据，把 164 页里 4 页正常银行流水全判成坏。"""
        rows = "\n".join(
            f"2026{i % 12 + 1:02d}{i % 28 + 1:02d} 转账 收入 {1000 + i}.00 {20000 + i}.55 62000000000000{i}"
            for i in range(200)
        )
        assert len(rows) > 5000, "用例本身要保证超过 5000 字"
        assert degeneracy_reason(rows, "stop") == ""

    def test_合法银行流水页不算复读_结构串每行都出现(self) -> None:
        """回归：数「某个窗口出现几次」把某 93 页卷宗的 p80/p81（8550/9039 字真实交易明细）判死。

        根因：`<td>账号</td><td>银联无卡快捷业务联机待清</td>` 这段结构串每行都有，
        单窗口数到 18 次；改成看去重比后该页 0.89–0.97，离阀值 0.25 很远。
        """
        rows = "\n".join(
            f"<tr><td>2025-11-{i % 28 + 1:02d} 10:04:16</td><td>转账</td><td>-{i + 1}.00</td>"
            f"<td>6200000000000000001</td><td>银联无卡快捷业务联机待清</td><td>{2000 - i}.15</td>"
            f"<td>财付通 | 协议支付 第{i}笔</td></tr>"
            for i in range(120)
        )
        assert len(rows) > 5000
        assert degeneracy_reason(rows, "stop") == ""

    def test_点号引导线的目录页不算复读(self) -> None:
        """目录页的 `......` 天然重复，但窗口里汉字不够，不参与复读判据。"""
        body = "\n".join(f"{i}. 证据材料名称第{i}项 ................................ {i * 7}" for i in range(60))
        assert degeneracy_reason(body, "stop") == ""

    def test_只被截断但内容不重复_正文仍可用(self) -> None:
        body = "\n".join(f"第{i}条：这是第{i}项不同的内容，写在合同第{i}条" for i in range(40))
        assert degeneracy_reason(body, "length") == ""

    def test_同一行重复4次仍在容忍范围(self) -> None:
        """真实银行流水里同一行最多出现 3-4 次（同一笔摘要）。门槛 5 是刻意留的余量。"""
        body = "\n".join(["财付通支付 50.00 余额 6773.95"] * 4 + [f"第{i}笔 转账 {i}.00" for i in range(20)])
        assert degeneracy_reason(body, "stop") == ""

    def test_短行高频不算复读(self) -> None:
        """表格页里 `1` / `---` / `|` 天然高频，短行不参与重复判据。"""
        body = "\n".join(["1\n---\n|\n2\n---\n|\n3\n---\n|"] * 10 + ["真实正文若干"])
        assert degeneracy_reason(body, "stop") == ""

    def test_正常正文完全放行(self) -> None:
        assert degeneracy_reason(REAL_BODY, "stop") == ""
        assert is_degenerate(REAL_BODY, "stop") is False


class TestStripCloudMarkers:
    def test_剥掉HTML标签与块类型词(self) -> None:
        raw = "<｜ref｜>table\uff5c[[0,0,999,999]]\uff5c> <table><tr><td>4. 某税务事项通知书</td></tr></table>"
        cleaned = strip_cloud_markers(raw)
        assert "table" not in cleaned
        assert "[[0,0,999,999]]" not in cleaned
        assert "4. 某税务事项通知书" in cleaned

    def test_没有标记时原样返回(self) -> None:
        assert strip_cloud_markers(REAL_BODY).strip() == REAL_BODY.strip()

    def test_None与空串不炸(self) -> None:
        assert strip_cloud_markers(None) == ""
        assert strip_cloud_markers("") == ""


class TestRealRegressions:
    def test_617的p1与p3与p33被判坏(self) -> None:
        """这两个形态来自 617 卷宗实跑：p1/p3/p33 三页整本调用时全部复读。"""
        for line in ("姓名 某某某", "登记机关 某市市场监督管理局", "1"):
            looped = "\n".join([line] * 300)
            assert is_degenerate(looped, "length") is True

    def test_617的p5授权委托书不被误判(self) -> None:
        assert is_degenerate(REAL_BODY, "stop") is False
