from apps.litigation_ai.services.placeholder_render_service import PlaceholderRenderService


def test_placeholder_render_service_idempotent_single():
    service = PlaceholderRenderService()
    template = "案件名称：{case_name}；案由：{cause}；缺失：{missing}"
    rendered1, stats1 = service.render(template, {"case_name": "测试案件", "cause": "合同纠纷"}, syntax="single")
    rendered2, stats2 = service.render(rendered1, {"case_name": "测试案件", "cause": "合同纠纷"}, syntax="single")

    assert rendered1 == rendered2
    assert set(stats1.placeholders_hit) == {"case_name", "cause"}
    assert stats1.placeholders_missed == ["missing"]
    assert stats2.placeholders_found == ["missing"]


def test_placeholder_render_service_double_brace():
    service = PlaceholderRenderService()
    template = "{{审理机构}} / {{ 起诉状当事人信息 }}"
    rendered, stats = service.render(template, {"审理机构": "A法院"}, syntax="double")

    assert rendered == "A法院 / {{ 起诉状当事人信息 }}"
    assert stats.placeholders_hit == ["审理机构"]
    assert stats.placeholders_missed == ["起诉状当事人信息"]
