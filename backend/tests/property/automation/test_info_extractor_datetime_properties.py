from datetime import datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.services.court_document_recognition import InfoExtractor


@st.composite
def safe_text_strategy(draw, *, min_size: int = 0, max_size: int = 2000) -> str:
    return draw(  # type: ignore[no-any-return]
        st.text(
            min_size=min_size,
            max_size=max_size,
            alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),  # type: ignore[arg-type]
        )
    )


@st.composite
def safe_date_time_strategy(draw):
    year = draw(st.integers(min_value=2020, max_value=2030))
    month = draw(st.integers(min_value=1, max_value=12))
    day = draw(st.integers(min_value=1, max_value=28))
    hour = draw(st.integers(min_value=0, max_value=23))
    minute = draw(st.integers(min_value=0, max_value=59))
    return year, month, day, hour, minute


@pytest.mark.property
@given(safe_date_time_strategy())
@settings(max_examples=60, deadline=None)
def test_extract_datetime_by_regex_iso_format(dt_tuple):
    year, month, day, hour, minute = dt_tuple
    text = f"开庭时间 {year}-{month}-{day} {hour}:{minute}"

    extractor = InfoExtractor()
    results = extractor._extract_datetime_by_regex(text)

    expected = datetime(year, month, day, hour, minute)
    assert any(r[0] == expected for r in results)


@pytest.mark.property
@given(
    year=st.integers(min_value=2020, max_value=2030),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
    am_pm=st.sampled_from(["上午", "下午"]),
    hour=st.integers(min_value=1, max_value=12),
    minute=st.integers(min_value=0, max_value=59),
)
@settings(max_examples=80, deadline=None)
def test_extract_datetime_by_regex_chinese_am_pm(year, month, day, am_pm, hour, minute):
    text = f"到庭应到时间{year}年{month}月{day}日{am_pm}{hour}时{minute}分"

    extractor = InfoExtractor()
    results = extractor._extract_datetime_by_regex(text)

    expected_hour = hour
    if am_pm == "下午" and hour < 12:
        expected_hour = hour + 12
    if am_pm == "上午" and hour == 12:
        expected_hour = 0

    expected = datetime(year, month, day, expected_hour, minute)
    assert any(r[0] == expected for r in results)


@pytest.mark.property
@given(prefix=safe_text_strategy(max_size=200), suffix=safe_text_strategy(max_size=200))
@settings(max_examples=80, deadline=None)
def test_extract_datetime_by_regex_never_crash(prefix: str, suffix: str):
    extractor = InfoExtractor()
    results = extractor._extract_datetime_by_regex(prefix + suffix)

    for dt, matched_text, context_score in results:
        assert isinstance(dt, datetime)
        assert isinstance(matched_text, str)
        assert isinstance(context_score, int)
        assert 2020 <= dt.year <= 2030
        assert 1 <= dt.month <= 12
        assert 1 <= dt.day <= 31
        assert 0 <= dt.hour <= 23
        assert 0 <= dt.minute <= 59
