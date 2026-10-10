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


def test_extract_main_text_keeps_numbered_fee_clause_in_mediation() -> None:
    """调解书把诉讼费写进编号条款（二、案件受理费…）时，不应在此截断，
    否则会丢失其后关键的强制执行触发条款（三、若…有权申请强制执行）。"""
    extractor = JudgmentPdfExtractor()
    text = (
        "（2026）粤0606民初16997号\n"
        "民事调解书\n"
        "经本院主持调解，双方当事人自愿达成如下协议：\n"
        "一、双方一致确认被告天津市某经营部、袁某尚欠原告广东某公司货款201797元；\n"
        "二、案件受理费减半收取计2196元，财产保全费1550.68元，合计3746.68元，"
        "由被告天津市某经营部、袁某负担并于2027年6月28日前向原告广东某公司支付完毕；\n"
        "三、若被告天津市某经营部、袁某有任何一期未按时足额支付，"
        "则原告广东某公司有权以尚欠货款、利息、财产保全费、案件受理费为总额"
        "一次性向法院申请强制执行。\n"
        "上述协议，不违反法律规定，本院予以确认。\n"
        "本调解书生效后，负有履行义务的当事人须依法按期履行全部义务。\n"
        "审判长 张三\n"
        "书记员 李四\n"
    )

    content = extractor._extract_main_text(text)

    assert content is not None
    assert "一、双方一致确认" in content
    assert "二、案件受理费" in content
    assert "三、若被告" in content
    assert "一次性向法院申请强制执行" in content
    assert "本调解书生效后" not in content
    assert "审判长" not in content
