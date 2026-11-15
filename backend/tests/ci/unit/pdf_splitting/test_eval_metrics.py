"""eval_metrics：CER / 归一化 / 表格 cell F1。

这三个函数是后续所有质量改动的度量尺。尺子本身错了，改动的结论全反——
所以每个用例都盯住一个**具体的错法**，而不是「跑通不报错」：

- CER 必须对**插入/删除**敏感（OCR 最常见的错不是等长替换）
- 归一化必须证明自己**真降了 CER**，否则报告里两个数就没区别
- cell F1 必须对**重复格**计数（流水表 40 行「财付通支付」，用 set 会全部压成 1）
"""

from __future__ import annotations

import pytest

from apps.pdf_splitting.services.split.eval_metrics import char_error_rate, normalize_for_cer, table_cell_f1


class TestCharErrorRate:
    def test_identical_is_zero(self) -> None:
        assert char_error_rate("中华人民共和国", "中华人民共和国") == 0.0

    def test_completely_different_is_one(self) -> None:
        # 等长全错：3 处替换 / 3 个参考字符 = 1.0
        assert char_error_rate("甲乙丙", "一二三") == 1.0

    def test_single_substitution(self) -> None:
        # 「起诉状」→「起诉书」：1 处替换 / 3 字
        assert char_error_rate("起诉书", "起诉状") == pytest.approx(1 / 3)

    def test_single_deletion(self) -> None:
        # 漏认一字：「张三丰」→「张三」= 1 处删除 / 3 字
        assert char_error_rate("张三", "张三丰") == pytest.approx(1 / 3)

    def test_single_insertion(self) -> None:
        # 多认一字：「张三」→「张三丰」= 1 处插入 / 参考 2 字 → 0.5
        assert char_error_rate("张三丰", "张三") == pytest.approx(0.5)

    def test_insertion_makes_cer_exceed_one(self) -> None:
        # 参考只有 2 字而预测 10 字：编辑距离 8 / 2 = 4.0
        # 刻意**不截断到 1.0**——截断会把「多认了 4 倍的字」和「全错」压成同一个数
        assert char_error_rate("0123456789", "01") == pytest.approx(4.0)

    def test_empty_reference_with_empty_prediction(self) -> None:
        assert char_error_rate("", "") == 0.0

    def test_empty_reference_with_nonempty_prediction(self) -> None:
        # 无参考却认出了字：无从判断对错，按全错记（而不是除零）
        assert char_error_rate("多出来的字", "") == 1.0

    def test_empty_prediction_scores_as_miss(self) -> None:
        # 整页没认出来：4 处删除 / 4 字 = 1.0
        assert char_error_rate("", "风险告知书") == 1.0

    def test_cer_is_asymmetric_by_definition(self) -> None:
        # CER 的分母是**参考**长度，所以换边必然不等：这是定义，不是 bug。
        # 「漏认 1 字」(参考 5 字) = 0.2；「多认 1 字」(参考 4 字) = 0.25。
        # 这条用例钉住 divisor，防止有人「优化」成对称平均就悄悄改了度量口径。
        assert char_error_rate("abde", "abcde") == pytest.approx(0.2)
        assert char_error_rate("abcde", "abde") == pytest.approx(0.25)


class TestNormalizeForCer:
    def test_markdown_heading_marker_removed(self) -> None:
        assert normalize_for_cer("## 风险告知书") == "风险告知书"

    def test_markdown_list_marker_removed(self) -> None:
        assert normalize_for_cer("- 第一条\n- 第二条") == "第一条第二条"

    def test_inline_emphasis_removed(self) -> None:
        assert normalize_for_cer("**加粗**与*斜体*") == "加粗与斜体"

    def test_table_separator_row_removed(self) -> None:
        # `| --- | :---: |` 是纯排版，参考侧没有对应内容
        assert normalize_for_cer("| 模块 | 参数项 |\n| --- | :---: |\n| 押品 | 编号 |") == "|模块|参数项||押品|编号|"

    def test_full_width_and_half_width_unified(self) -> None:
        # NFKC：全角括号/字母/数字与半角等价
        assert normalize_for_cer("（Ａ）（1）") == normalize_for_cer("(A)(1)")

    def test_whitespace_removed_entirely(self) -> None:
        # 换行位置是引擎差异，不承载内容
        assert normalize_for_cer("第一行\n第二行\t第三行　第四行") == "第一行第二行第三行第四行"

    def test_content_characters_untouched(self) -> None:
        # 归一化只去格式，正文一个字都不许动
        src = "兹证明曾妙焮老师月收入11700元。"
        assert normalize_for_cer(src) == src

    def test_normalization_reduces_cer_for_pure_formatting(self) -> None:
        # 归一化的意义就在这里：只差排版时，归一化后 CER 必须为 0 而原样不为 0
        gold = "风险告知书"
        pred = "## 风险 告知书"
        assert char_error_rate(pred, gold) > 0
        assert char_error_rate(normalize_for_cer(pred), normalize_for_cer(gold)) == 0.0


class TestTableCellF1:
    def test_identical_html_is_one(self) -> None:
        html = "<table><tr><td>押品信息</td><td>*房产证编号</td></tr></table>"
        assert table_cell_f1(html, html) == 1.0

    def test_identical_gfm_is_one(self) -> None:
        gfm = "| 模块 | 参数项 |\n| --- | --- |\n| 押品信息 | *房产证编号 |"
        assert table_cell_f1(gfm, gfm) == 1.0

    def test_html_and_gfm_of_same_table_match(self) -> None:
        # pipeline 输出 GFM、golden 存 HTML：两种形态必须能互比，否则打分恒为 0
        html = "<table><tr><td>模块</td><td>参数项</td></tr><tr><td>押品信息</td><td>编号</td></tr></table>"
        gfm = "| 模块 | 参数项 |\n| --- | --- |\n| 押品信息 | 编号 |"
        assert table_cell_f1(gfm, html) == 1.0

    def test_row_and_column_order_ignored(self) -> None:
        # 不要求行列对齐：格内容集合相同即满分（坐标是均分推算的，对齐无意义）
        gold = "<table><tr><td>甲</td><td>乙</td></tr></table>"
        pred = "<table><tr><td>乙</td></tr><tr><td>甲</td></tr></table>"
        assert table_cell_f1(pred, gold) == 1.0

    def test_missing_cell_lowers_recall(self) -> None:
        gold = "<table><tr><td>甲</td><td>乙</td><td>丙</td><td>丁</td></tr></table>"
        pred = "<table><tr><td>甲</td><td>乙</td><td>丙</td></tr></table>"
        # precision=1.0，recall=3/4 → F1 = 2*1*0.75/1.75 = 0.857
        assert table_cell_f1(pred, gold) == pytest.approx(2 * 1.0 * 0.75 / 1.75)

    def test_extra_cell_lowers_precision(self) -> None:
        gold = "<table><tr><td>甲</td><td>乙</td></tr></table>"
        pred = "<table><tr><td>甲</td><td>乙</td><td>丙</td><td>丁</td></tr></table>"
        # recall=1.0，precision=2/4 → F1 = 2*0.5*1/1.5 = 0.667
        assert table_cell_f1(pred, gold) == pytest.approx(2 * 0.5 * 1.0 / 1.5)

    def test_duplicate_cells_counted_multiplicity(self) -> None:
        # 流水表里「财付通支付」重复 40 次：用 set 会压成 1 次，掩盖漏行。
        # 这里预测 3 行、参考 5 行，同样的格 → precision=1，recall=3/5
        gold = "<table>" + "<tr><td>财付通支付</td></tr>" * 5 + "</table>"
        pred = "<table>" + "<tr><td>财付通支付</td></tr>" * 3 + "</table>"
        assert table_cell_f1(pred, gold) == pytest.approx(2 * 1.0 * 0.6 / 1.6)

    def test_img_only_cells_ignored(self) -> None:
        # 纯图形格（结婚证照片）不承载文字，不该拉低分数
        gold = '<table><tr><td><img src="a.jpg"/></td><td>登记机</td></tr></table>'
        pred = "<table><tr><td>登记机</td></tr></table>"
        assert table_cell_f1(pred, gold) == 1.0

    def test_whitespace_inside_cell_is_irrelevant(self) -> None:
        gold = "<table><tr><td> 押品信息 </td></tr></table>"
        pred = "<table><tr><td>押品信息</td></tr></table>"
        assert table_cell_f1(pred, gold) == 1.0

    def test_completely_different_is_zero(self) -> None:
        gold = "<table><tr><td>甲</td></tr></table>"
        pred = "<table><tr><td>己</td></tr></table>"
        assert table_cell_f1(pred, gold) == 0.0

    def test_both_empty_is_one(self) -> None:
        # 两侧都没有可比的格：没有可错的，记满分而非 0
        assert table_cell_f1("", "") == 1.0

    def test_one_side_empty_is_zero(self) -> None:
        gold = "<table><tr><td>甲</td></tr></table>"
        assert table_cell_f1("", gold) == 0.0
        assert table_cell_f1(gold, "") == 0.0
