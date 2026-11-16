"""``md_noise``：HTML 净化 / 段标题去重 / 跨页重复短行噪声。

测试数据全部虚构。印章核验语用银行档案里真实出现的**短语形态**（不含任何人名），
条款号/金额日期保护判据用法院文书与合同的典型行形态——两类材料都要守住。
"""

from __future__ import annotations

from apps.pdf_splitting.services.split.md_noise import (
    MAX_NOISE_LINE_CHARS,
    drop_noise_lines,
    drop_stamp_boilerplate_lines,
    is_stamp_boilerplate_line,
    normalize_title,
    repeated_noise_lines,
    strip_html,
    title_already_present,
)


class TestStripHtml:
    def test_img_直接去除不留占位文字(self) -> None:
        text = '面谈笔录<img src="imgs/img_in_image_box_1_2_3_4.jpg" alt="Image">'
        assert strip_html(text) == "面谈笔录"

    def test_div_去壳留内文(self) -> None:
        assert strip_html("<div>第一段</div><div>第二段</div>") == "第一段第二段"

    def test_br_换成换行(self) -> None:
        assert strip_html("第一行<br>第二行<br/>第三行") == "第一行\n第二行\n第三行"

    def test_实体反转义(self) -> None:
        assert strip_html("甲方&amp;乙方&lt;丙&gt;") == "甲方&乙方<丙>"

    def test_比较号不被当标签吃掉(self) -> None:
        """法律正文里「金额<100万」「利率>4%」是常态，通吃正则会整段吞掉。"""
        text = "借款金额<100万元，年利率>4%，逾期<30天>另计"
        assert strip_html(text) == text

    def test_无标签文本原样(self) -> None:
        assert strip_html("  普通正文\n第二行  ") == "普通正文\n第二行"
        assert strip_html("") == ""

    def test_表格标签也剥掉(self) -> None:
        assert strip_html("<table><tr><td>金额</td><td>100.00</td></tr></table>") == "金额100.00"


class TestTitleDedup:
    def test_同名标题不再重复注入(self) -> None:
        assert title_already_present("个人房产抵押贷款合同", "## 个人房产抵押贷款合同") is True

    def test_标点空白与全角差异归一后相等(self) -> None:
        assert normalize_title("个人贷款合同（2017）") == normalize_title("个人贷款合同(2017)")
        assert title_already_present("个人贷款合同（2017）", "# 个人贷款合同 (2017)") is True

    def test_不同名保留注入(self) -> None:
        assert title_already_present("借款合同", "## 个人房产抵押贷款合同") is False

    def test_首行不是标题时保留注入(self) -> None:
        assert title_already_present("借款合同", "甲方与乙方经协商…") is False

    def test_空段名不去重(self) -> None:
        assert title_already_present("", "## ") is False

    def test_带续字后缀不算同名(self) -> None:
        assert title_already_present("贷款申请核实清单_续", "## 贷款申请核实清单") is False


class TestRepeatedNoiseLines:
    """印章核验语这类「每页盖一次」的短行才滤；正文结构行一律保护。"""

    STAMP = "已核对与原件相符"

    def test_三页以上且过半重复才命中(self) -> None:
        pages = [[f"正文第{i}段", self.STAMP] for i in range(4)]
        assert repeated_noise_lines(pages) == {self.STAMP}

    def test_只有两页不命中(self) -> None:
        assert repeated_noise_lines([[self.STAMP], [self.STAMP]]) == set()

    def test_重复页数够但占比不足不命中(self) -> None:
        pages = [[self.STAMP], [self.STAMP], [self.STAMP], *[[f"正文{i}"] for i in range(7)]]
        assert repeated_noise_lines(pages) == set()

    def test_占比够但页数不足不命中(self) -> None:
        # 2/2 = 100% 但只有 2 页
        assert repeated_noise_lines([[self.STAMP], [self.STAMP, "别的"]]) == set()

    def test_条款编号行受保护(self) -> None:
        for line in ("第一条 借款用途", "第3条 利率", "1.1 借款本金", "一、借款金额", "2、还款方式"):
            pages = [[line, f"正文第{i}段"] for i in range(4)]
            assert repeated_noise_lines(pages) == set(), line

    def test_金额日期账号行受保护(self) -> None:
        for line in ("20170201", "100.00", "2017年1月", "余额 6697.95"):
            pages = [[line, f"正文第{i}段"] for i in range(4)]
            assert repeated_noise_lines(pages) == set(), line

    def test_页码形态不受数字保护但需满足重复判据(self) -> None:
        # 「第2页」只有单个数字，不算金额日期 → 每页重复时可以被滤
        pages = [["第2页", f"正文第{i}段"] for i in range(4)]
        assert repeated_noise_lines(pages) == {"第2页"}

    def test_表格行与标题行受保护(self) -> None:
        pages = [["| 交易日期 | 金额 |", "| --- | --- |", "## 民事判决书"]] * 4
        assert repeated_noise_lines(pages) == set()

    def test_超长行不参与统计(self) -> None:
        long_line = "已核对与原件相符" + "正文" * MAX_NOISE_LINE_CHARS
        assert repeated_noise_lines([[long_line]] * 4) == set()

    def test_空页不计入分母(self) -> None:
        assert repeated_noise_lines([]) == set()


class TestDropNoiseLines:
    def test_只删噪声行保留行序(self) -> None:
        text = "第一条 借款\n已核对与原件相符\n借款金额 100.00 元\n扫描件与留档资料相符\n此致"
        noise = {"已核对与原件相符", "扫描件与留档资料相符"}
        assert drop_noise_lines(text, noise) == "第一条 借款\n借款金额 100.00 元\n此致"

    def test_无噪声集合时原样返回(self) -> None:
        text = "第一行\n第二行"
        assert drop_noise_lines(text, set()) is text

    def test_带缩进的噪声行也删(self) -> None:
        assert drop_noise_lines("  已核对与原件相符  \n正文", {"已核对与原件相符"}) == "正文"


class TestStampBoilerplateLine:
    """短语锚定路：整行是已知印章套话才剔，不依赖页频（单页段也生效）。

    短语判据复用 ``page_quality.strip_stamp_boilerplate_lines``，这里只测
    「整行 vs 混合」的边界与防误剔守卫。人名一律用「测试甲/测试乙」。
    """

    def test_单行纯套话命中(self) -> None:
        assert is_stamp_boilerplate_line("已核对与原件相符") is True
        assert is_stamp_boilerplate_line("扫描件与留档资料相符") is True
        assert is_stamp_boilerplate_line("已核对与原件相符扫描件与留档资料相符") is True

    def test_经办人整行命中(self) -> None:
        assert is_stamp_boilerplate_line("经办人：测试甲 测试乙") is True
        assert is_stamp_boilerplate_line("经办人: 测试甲 测试乙") is True
        assert is_stamp_boilerplate_line("经办人：测试甲测试乙") is True  # OCR 粘连变体
        assert is_stamp_boilerplate_line("经办人：") is True
        # 人名与套话粘成一个 token：形态校验要看剥掉套话后的残留
        assert is_stamp_boilerplate_line("经办人: 测试甲 测试乙已核对与原件相符") is True

    def test_套话与条款正文同行不剔(self) -> None:
        assert is_stamp_boilerplate_line("已核对与原件相符 第一条 借款用途") is False
        assert is_stamp_boilerplate_line("经办人：测试甲 测试乙 借款人应按期还款") is False

    def test_法院文书正文零误剔(self) -> None:
        for line in (
            "本院认为，被告应偿还借款。",
            "如不服本判决，可在判决书送达之日起十五日内上诉。",
            "第一条 借款用途",
            "审判长 测试甲",
            "书记员 测试乙",
        ):
            assert is_stamp_boilerplate_line(line) is False, line

    def test_含金额账号日期零误剔(self) -> None:
        for line in (
            "经办人：测试甲 日期：2023.2.15",
            "已核对与原件相符 余额 6697.95",
            "经办人：测试甲 卡号 6223221027175157",
            "扫描件与留档资料相符 20170201",
            "经办人：测试甲 2017年1月",
        ):
            assert is_stamp_boilerplate_line(line) is False, line

    def test_贪婪经办人尾巴吞正文时不剔(self) -> None:
        """579 实测形态：判据里「经办人[:：]」贪婪到行尾，会把后面的正文一起吞掉。"""
        for line in (
            "经办人：测试甲 测试乙根据《中华人民共和国物权法》等法律法规，准予登记，颁发此证。",
            "经办人：测试甲 测试乙实施 FATCA 法案尽职调查",
            "经办人：测试甲 测试乙中华人民共和国国土资源部监制",
            "经办人：测试甲 测试乙某某银行个人贷款面谈笔录表",
        ):
            assert is_stamp_boilerplate_line(line) is False, line

    def test_表格行与标题行不剔(self) -> None:
        assert is_stamp_boilerplate_line("| 已核对与原件相符 经办人：测试甲 |  |") is False
        assert is_stamp_boilerplate_line("# 已核对与原件相符") is False

    def test_普通正文与空行不命中(self) -> None:
        assert is_stamp_boilerplate_line("借款金额 100.00 元") is False
        assert is_stamp_boilerplate_line("") is False
        assert is_stamp_boilerplate_line("   ") is False


class TestDropStampBoilerplateLines:
    def test_单页文本里的套话行被剔而正文保留(self) -> None:
        text = (
            "个人贷款面谈笔录表\n已核对与原件相符\n扫描件与留档资料相符\n"
            "经办人：测试甲 测试乙\n借款人确认以上信息属实。"
        )
        assert drop_stamp_boilerplate_lines(text) == "个人贷款面谈笔录表\n借款人确认以上信息属实。"

    def test_无套话时原样返回(self) -> None:
        text = "第一行\n第二行\n"
        assert drop_stamp_boilerplate_lines(text) is text

    def test_混合行原样保留不改写(self) -> None:
        text = "⑤报告所称抵押价值是估价对象假定未设立法定优先受偿权下的价值。已核对与原件相符"
        assert drop_stamp_boilerplate_lines(text) == text

    def test_整块都是套话时清空(self) -> None:
        assert drop_stamp_boilerplate_lines("已核对与原件相符\n经办人：测试甲 测试乙") == ""
