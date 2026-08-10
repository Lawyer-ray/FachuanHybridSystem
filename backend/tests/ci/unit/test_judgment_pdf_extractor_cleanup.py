from __future__ import annotations

from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor


def test_extract_main_text_removes_inline_page_noise() -> None:
    extractor = JudgmentPdfExtractor()
    text = (
        "经本院主持调解，双方当事人自愿达成如下协议："
        "一、原、被告一致确认，截至2025年11月5日两被告尚欠原告货款100592.83元；"
        "四、若两被告任何一期未能按时足额支付上述款项，原告有权要求两被告支付逾期付款利息"
        "（以100592.83第3页共3页元的剩余未付款项为基数，自2025年7月1日起按年利率4.5%计算至实际清偿之日止）；"
        "如不服本调解书，可在送达之日起十五日内上诉。"
    )

    content = extractor._extract_main_text(text)

    assert content is not None
    assert "第3页共3页" not in content
    assert "100592.83元的剩余未付款项为基数" in content


def test_sanitize_text_removes_page_of_pattern() -> None:
    extractor = JudgmentPdfExtractor()
    raw = "判决如下：Page2of5被告应支付货款1000元。"

    cleaned = extractor._sanitize_extracted_text(raw)

    assert "Page2of5" not in cleaned
    assert cleaned == "判决如下：被告应支付货款1000元。"


def test_sanitize_text_keeps_legal_article_reference() -> None:
    extractor = JudgmentPdfExtractor()
    raw = "如果未按本判决指定的期间履行给付金钱义务，应当依照《中华人民共和国民事诉讼法》第二百六十四条规定。"

    cleaned = extractor._sanitize_extracted_text(raw)

    assert "第二百六十四条" in cleaned
    assert cleaned == raw


def test_extract_main_text_keeps_second_instance_affirmation() -> None:
    """二审维持原判的判决书：主文本身是'驳回上诉，维持原判'，不应被当成截止关键词截断掉。"""
    extractor = JudgmentPdfExtractor()
    text = (
        "（2026）粤06民终7433号\n"
        "民事判决书\n"
        "上诉人因追偿权纠纷一案，不服一审判决提起上诉。本院二审审理终结。\n"
        "判决如下：\n"
        "驳回上诉，维持原判。\n"
        "本判决为终审判决。\n"
        "案件受理费100元由上诉人负担。\n"
        "审判长 张三\n"
        "书记员 李四\n"
    )

    content = extractor._extract_main_text(text)

    assert content is not None
    assert "驳回上诉，维持原判" in content
    assert "本判决为终审判决" not in content
    assert "案件受理费" not in content
    assert "审判长" not in content
