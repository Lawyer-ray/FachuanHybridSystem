def test_contract_docx_filename_contains_version_and_suffix():
    from apps.documents.services.generation.pipeline.naming import contract_docx_filename

    value = contract_docx_filename(template_name="模板.docx", contract_name="合同A", version="V9")
    assert value.endswith(".docx")
    assert "V9_" in value
    assert "模板" in value
    assert "合同A" in value


def test_supplementary_agreement_docx_filename_contains_version_and_suffix():
    from apps.documents.services.generation.pipeline.naming import supplementary_agreement_docx_filename

    value = supplementary_agreement_docx_filename(agreement_name="补充一", contract_name="合同A", version="V2")
    assert value.endswith(".docx")
    assert "V2_" in value
    assert "补充一" in value
    assert "合同A" in value
