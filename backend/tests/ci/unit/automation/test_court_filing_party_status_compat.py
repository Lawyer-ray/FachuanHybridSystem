"""一张网立案：当事人诉讼地位的**中英文混存**兼容。

═════ 这组测试守的是一个线上真实缺陷 ═════
生产库 `cases_caseparty.legal_status` 是混存的（实测）：
    defendant 73 / plaintiff 45 / respondent 33 / applicant 29 /
    criminal_defendant 13 / appellant 11 / 被告 3 / …
早期 `_PLAINTIFF_SIDE_STATUSES` 只收英文。后果是一条完整的假失败链：
  ① 中文「原告/被告」不在任一集合 → plaintiffs/defendants 都为空
  ② `/court-filing/case-info` 返回 plaintiff_name=null、our_party_is_plaintiff_side=false
  ③ 前端据此显示「我方不是原告方，本页只处理起诉立案」并禁用按钮
  ④ 律师看到的诊断完全错误 —— 我方明明就是原告，只是数据写的是中文

同一个坑在 `apps/cases/services/case_readiness_service.py` 也踩过（那边已修），
两处的状态口径必须一致，这组测试盯住 court_automation 这一侧。
"""

from __future__ import annotations

from types import SimpleNamespace

from plugins.court_automation.filing.helpers import _build_party_payloads


def _party(legal_status: str, name: str, *, client_type: str = "natural") -> SimpleNamespace:
    """造一个 CaseParty 形状的对象（带 client 关联）。"""
    return SimpleNamespace(
        legal_status=legal_status,
        client=SimpleNamespace(
            client_type=client_type,
            name=name,
            address="佛山市某某区某某路 1 号",
            # 联系方式用明显非真实号码的占位（避免与真实手机号格式混淆）
            phone="000-0000-0000",
            id_number="440681199001011234" if client_type == "natural" else "91440606MA5D8XK73T",
            legal_representative="" if client_type == "natural" else "陈某某",
            legal_representative_id_number="" if client_type == "natural" else "440601197001011111",
        ),
    )


class TestChineseLegalStatus:
    """中文诉讼地位必须被识别（与英文等价）。"""

    def test_chinese_plaintiff_and_defendant(self) -> None:
        parties = [
            _party("原告", "某某银行股份有限公司佛山城南支行", client_type="legal_entity"),
            _party("被告", "谭某某"),
            _party("被告", "梁某某"),
        ]
        plaintiffs, defendants, third_parties = _build_party_payloads(parties)

        assert len(plaintiffs) == 1, "中文「原告」应被算作原告"
        assert len(defendants) == 2, "中文「被告」应被算作被告"
        assert third_parties == []
        assert plaintiffs[0]["name"] == "某某银行股份有限公司佛山城南支行"
        assert defendants[0]["name"] == "谭某某"

    def test_chinese_third_party(self) -> None:
        parties = [_party("第三人", "某某担保有限公司", client_type="legal_entity")]
        _, _, third_parties = _build_party_payloads(parties)
        assert len(third_parties) == 1

    def test_chinese_appeal_sides(self) -> None:
        """二审：上诉人 / 被上诉人 也要分得清。"""
        parties = [_party("上诉人", "吴某某"), _party("被上诉人", "某某银行")]
        plaintiffs, defendants, _ = _build_party_payloads(parties)
        # 上诉人属于原告侧、被上诉人属于被告侧（court_automation 的分侧口径）
        assert len(plaintiffs) == 1 and plaintiffs[0]["name"] == "吴某某"
        assert len(defendants) == 1 and defendants[0]["name"] == "某某银行"

    def test_english_still_works(self) -> None:
        """不能因为兼容中文而弄坏英文（这是回归红线）。"""
        parties = [_party("plaintiff", "A 银行"), _party("defendant", "B 某")]
        plaintiffs, defendants, _ = _build_party_payloads(parties)
        assert len(plaintiffs) == 1
        assert len(defendants) == 1

    def test_unknown_status_dropped(self) -> None:
        """真认不出的状态不硬塞进任何一侧——宁可缺，也不要错填。"""
        parties = [_party("witness", "旁观者")]
        plaintiffs, defendants, third_parties = _build_party_payloads(parties)
        assert plaintiffs == [] and defendants == [] and third_parties == []
