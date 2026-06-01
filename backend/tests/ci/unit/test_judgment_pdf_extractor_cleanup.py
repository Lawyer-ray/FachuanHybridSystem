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
