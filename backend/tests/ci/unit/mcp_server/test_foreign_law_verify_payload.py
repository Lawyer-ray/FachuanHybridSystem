"""`asean_law_verify` 的返回契约：合议结论面必须透出，不许在中途被丢掉。

## 为什么要单独立一个契约测试

`asean_law_verify` 曾经是**手挑字段**拼返回值：插件里算好的 `elements / votes /
needs_human / agreement` 全部被丢掉，只留下一句 `reason` 散文。后果是 AI 助手
没法回答「哪一项没依据」，审计链也断了。

这类「算完了又被丢掉」的回归靠读代码看不出来（代码两边都对），必须钉一个
**对返回值键集的断言**：插件将来多算一个字段，这里就应该提醒去透出。

同时兜住一个语义坑：`needs_model_judgement` 曾经等于 `not result`，于是
「合议弃权」被冒充成「请外部判定层来判」。现在它必须区分
`adjudicated`（合议跑过，弃权也别再判）与未开启合议。

无网络、无数据库：适配器与凭据都被替换，判定器注入假实现。
"""

from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.unit

_HAS_PLUGIN = importlib.util.find_spec("plugins.barlc_asean_law") is not None
if not _HAS_PLUGIN:  # pragma: no cover - CI 无子模块时走这里
    pytest.skip("backend/plugins 子模块未检出，跳过域外法工具契约测试", allow_module_level=True)

from mcp_server.tools.foreign_law import asean_law
from plugins.barlc_asean_law import jury as jury_module
from plugins.barlc_asean_law.adapter import BarlcAdapter
from plugins.barlc_asean_law.credential import BarlcCredential
from plugins.barlc_asean_law.models import LawDetail, LawFile, LawHit, LawSection

CRED = BarlcCredential(credential_id=1, account="a@example.com", password="x", site_name="barlc")
SECTION_TEXT = "Section 4. Rental under this Act must be in writing and registered with the competent official."

#: 通过工具返回面必须能看到的键（少一个就是「算完又丢了」）。
REQUIRED_KEYS = {
    "ok",
    "verdict",
    "law_title",
    "section_number",
    "section_text",
    "reason",
    "claim",
    "adjudicated",
    "unconfirmed",
    "needs_model_judgement",
    "needs_human",
    "review_reasons",
    "agreement",
    "matched_by",
    "elements",
    "votes",
    "jury_tokens",
}


class _FakeAdapter:
    """最小假适配器：只回答"有一部法、有第 4 条"。"""

    def __init__(self, sections: list[LawSection] | None = None) -> None:
        self._sections = sections if sections is not None else [LawSection(number="4", text=SECTION_TEXT)]

    def search(self, credential, *, keyword, country_code=None, field="Title", page=1, page_size=20):
        hits = [
            LawHit(
                sys_id="321381",
                title_cn="1999年商业和工业房地产租赁法",
                title_en="Rental of Immovable Property for Commerce and Industry Act",
                title_local="",
                country_code="LAWCOUNTRYTG",
            )
        ]
        return 1, hits

    def get_detail(self, credential, *, sys_id):
        return LawDetail(
            sys_id=sys_id,
            title_cn="1999年商业和工业房地产租赁法",
            title_en="Rental of Immovable Property for Commerce and Industry Act",
            title_local="",
            publish_date=None,
            effective_date=None,
            revise_date=None,
            keywords_cn="",
            keywords_en="",
            country_code="LAWCOUNTRYTG",
            law_category="",
            has_english_pdf=True,
            file_count=1,
            files=[LawFile(record_id=1, file_id=1, filename="a.pdf", size=1)],
        )

    def fetch_sections(self, credential, *, detail, lang="en", allow_lang_fallback=True):
        return list(self._sections)

    @staticmethod
    def find_section(sections, number):
        return BarlcAdapter.find_section(sections, number)


def _judge_answer(elements: list[tuple[str, str]]) -> str:
    import json

    return json.dumps(
        {
            "elements": [
                {"statement": statement, "verdict": verdict, "reason": "依据"} for statement, verdict in elements
            ],
            "quote": "",
        },
        ensure_ascii=False,
    )


@pytest.fixture()
def wired(monkeypatch):
    """装上假适配器 + 假判定器，并把判定缓存清干净。"""
    adapter = _FakeAdapter()
    monkeypatch.setattr(asean_law, "_adapter_and_credential", lambda: (adapter, CRED))
    monkeypatch.delenv("FACHUAN_BARLC_JURY", raising=False)
    jury_module.reset_jury_cache()
    yield adapter
    jury_module.reset_jury_cache()


def test_verify_exposes_full_adjudication_payload(wired, monkeypatch) -> None:
    answer = _judge_answer([("必须书面", "支持"), ("必须登记", "支持")])
    monkeypatch.setattr(jury_module, "llm_judge_call", lambda prompt, model, role: (answer, 10))

    result = asean_law.asean_law_verify(
        law_name="Rental of Immovable Property for Commerce and Industry Act",
        section_number="Section 4",
        claim="租赁合同必须书面并登记",
        country_code="LAWCOUNTRYTG",
    )

    assert set(result) >= REQUIRED_KEYS, f"工具返回值缺字段：{REQUIRED_KEYS - set(result)}"
    assert result["verdict"] == "支持"
    assert result["adjudicated"] is True
    assert result["unconfirmed"] is False
    # 合议跑过了，就不能再说「请判定层来判」。
    assert result["needs_model_judgement"] is False
    assert result["agreement"] == 1.0
    assert [element["verdict"] for element in result["elements"]] == ["支持", "支持"]


def test_votes_are_trimmed_to_decision_surface(wired, monkeypatch) -> None:
    """投票明细进返回值时必须去自由文本——它会整段进模型上下文。"""
    answer = _judge_answer([("必须书面", "支持")])
    monkeypatch.setattr(jury_module, "llm_judge_call", lambda prompt, model, role: (answer, 10))

    result = asean_law.asean_law_verify(
        law_name="Rental of Immovable Property for Commerce and Industry Act",
        section_number="4",
        claim="租赁合同必须书面",
        country_code="LAWCOUNTRYTG",
    )

    assert len(result["votes"]) == 3
    for vote in result["votes"]:
        assert set(vote) == {"model", "role", "verdict", "unscored_reason", "evidence_ok", "attempts", "total_tokens"}
        assert "quote" not in vote
        assert "elements" not in vote


def test_abstention_is_not_reported_as_waiting_for_judgement(wired, monkeypatch) -> None:
    """判定器全挂 → 弃权。这是**合议的结论**，不能冒充「待外部判定层」。"""

    def _boom(prompt: str, model: str, role: str):
        raise RuntimeError("provider down")

    monkeypatch.setattr(jury_module, "llm_judge_call", _boom)

    result = asean_law.asean_law_verify(
        law_name="Rental of Immovable Property for Commerce and Industry Act",
        section_number="4",
        claim="租赁合同必须书面",
        country_code="LAWCOUNTRYTG",
    )

    assert result["verdict"] == "待判定"
    assert result["adjudicated"] is True
    assert result["unconfirmed"] is True
    assert result["needs_human"] is True
    assert result["needs_model_judgement"] is False


def test_jury_disabled_reports_pending_judgement(wired, monkeypatch) -> None:
    """合议关闭时才是真的「待判定层」——此时 needs_model_judgement 必须为真。"""
    monkeypatch.setenv("FACHUAN_BARLC_JURY", "off")

    result = asean_law.asean_law_verify(
        law_name="Rental of Immovable Property for Commerce and Industry Act",
        section_number="4",
        claim="租赁合同必须书面",
        country_code="LAWCOUNTRYTG",
    )

    assert result["verdict"] == "待判定"
    assert result["adjudicated"] is False
    assert result["needs_model_judgement"] is True


def test_unparsed_sections_are_unconfirmed_not_not_found(wired, monkeypatch) -> None:
    """切不出条款、名称只是近似时，不能报「不存在该引用」。"""
    wired._sections = []  # type: ignore[attr-defined]

    result = asean_law.asean_law_verify(
        law_name="Rental of Immovable Property for Commerce and Industry Act",
        section_number="4",
        claim="租赁合同必须书面",
        country_code="LAWCOUNTRYTG",
    )

    assert result["verdict"] == "待判定"
    assert result["unconfirmed"] is True
    assert result["needs_human"] is True
    assert "不等同于" in result["reason"]


def test_not_found_still_reported_as_not_found(wired, monkeypatch) -> None:
    """真正检索不到时仍然是「不存在该引用」（规则层判死，不消耗模型）。"""
    monkeypatch.setattr(wired, "search", lambda *args, **kwargs: (0, []))

    result = asean_law.asean_law_verify(law_name="Fake Thailand Lease Act 2099", section_number="1")

    assert result["verdict"] == "不存在该引用"
    assert result["unconfirmed"] is False
    assert result["needs_model_judgement"] is False
