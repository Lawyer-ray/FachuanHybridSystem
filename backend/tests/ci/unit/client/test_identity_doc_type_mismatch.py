"""证件类型与主体类型不匹配的回归测试。

背景（2026-11-06 实爆）：client 112 是法人主体，名下却有一条 doc_type=id_card 的历史脏行。
`ClientIdentityDoc.clean()` 里做主体/证件类型校验，而 Django 对 inline formset 的**每一行**
（含勾了「删除」的行）都会在 save 之前调 Model.full_clean() → clean()，DELETE 标记只在
save_existing_objects() 阶段生效，赶不上校验。结果整张表单「既存不下去也删不掉」。

修复两部分：
1. 校验从 Model.clean() 下沉到 ClientIdentityDocInlineForm.clean()，并按 DELETE 跳过；
2. 数据迁移 0018 把历史脏行归并到合法类型，且不丢真实文件。

本测试锁定这两点，防复发。
"""

from __future__ import annotations

import pytest
from django.forms import inlineformset_factory

from apps.client.admin.client_admin import ClientIdentityDocInlineForm
from apps.client.admin.clientidentitydoc_admin import ClientIdentityDocForm
from apps.client.models import Client, ClientIdentityDoc

pytestmark = pytest.mark.django_db


def _make_client(client_type: str = Client.LEGAL) -> Client:
    return Client.objects.create(name="测试当事人", client_type=client_type)


def _formset(client: Client):
    return inlineformset_factory(
        Client,
        ClientIdentityDoc,
        form=ClientIdentityDocInlineForm,
        fields=["doc_type"],
        extra=1,
        can_delete=True,
    )


def _payload(docs: list[ClientIdentityDoc], delete_idx: int | None = None) -> dict[str, str]:
    data = {
        "identity_docs-TOTAL_FORMS": str(len(docs) + 1),
        "identity_docs-INITIAL_FORMS": str(len(docs)),
        "identity_docs-MIN_NUM_FORMS": "0",
        "identity_docs-MAX_NUM_FORMS": "1000",
    }
    for i, doc in enumerate(docs):
        data[f"identity_docs-{i}-id"] = str(doc.pk)
        data[f"identity_docs-{i}-doc_type"] = doc.doc_type
    data[f"identity_docs-{len(docs)}-id"] = ""
    data[f"identity_docs-{len(docs)}-doc_type"] = ""
    if delete_idx is not None:
        data[f"identity_docs-{delete_idx}-DELETE"] = "on"
    return data


class TestModelValidationMethod:
    """校验方法本身仍然可用（只是不再叫 clean）。"""

    def test_legal_client_rejects_natural_doc_type(self):
        client = _make_client(Client.LEGAL)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.ID_CARD)
        with pytest.raises(Exception) as exc:
            doc.validate_doc_type_for_client()
        assert "Invalid doc type for organization" in str(exc.value)

    def test_legal_client_accepts_legal_doc_type(self):
        client = _make_client(Client.LEGAL)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.BUSINESS_LICENSE)
        doc.validate_doc_type_for_client()  # 不抛

    def test_natural_client_rejects_legal_doc_type(self):
        client = _make_client(Client.NATURAL)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.BUSINESS_LICENSE)
        with pytest.raises(Exception) as exc:
            doc.validate_doc_type_for_client()
        assert "Invalid doc type for natural person" in str(exc.value)

    def test_model_full_clean_no_longer_raises_for_mismatch(self):
        """关键回归：Model.clean() 不再拦这类行，否则 formset 的 DELETE 行会被锁死。"""
        client = _make_client(Client.LEGAL)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.ID_CARD)
        doc.full_clean(exclude={"client"})  # 不应抛 ValidationError


class TestInlineFormsetDeleteNotBlocked:
    """勾了删除的行不能被证件类型校验拦住。"""

    def test_delete_marked_row_with_invalid_doc_type_is_valid(self):
        client = _make_client(Client.LEGAL)
        ClientIdentityDoc.objects.create(client=client, doc_type=ClientIdentityDoc.BUSINESS_LICENSE)
        # 历史脏行：法人主体 + 身份证
        dirty = ClientIdentityDoc.objects.create(client=client, doc_type=ClientIdentityDoc.ID_CARD)

        docs = list(ClientIdentityDoc.objects.filter(client=client).order_by("pk"))
        idx = next(i for i, d in enumerate(docs) if d.pk == dirty.pk)
        fs = _formset(client)(_payload(docs, delete_idx=idx), instance=client)

        assert fs.is_valid(), fs.errors
        assert dirty in [f.instance for f in fs.deleted_forms]

        fs.save()
        assert not ClientIdentityDoc.objects.filter(pk=dirty.pk).exists()

    def test_non_deleted_invalid_row_still_rejected(self):
        """不勾删除时，非法类型仍必须报错——校验没有被整体关掉。"""
        client = _make_client(Client.LEGAL)
        dirty = ClientIdentityDoc.objects.create(client=client, doc_type=ClientIdentityDoc.ID_CARD)

        docs = list(ClientIdentityDoc.objects.filter(client=client).order_by("pk"))
        fs = _formset(client)(_payload(docs), instance=client)

        assert not fs.is_valid()
        idx = next(i for i, d in enumerate(docs) if d.pk == dirty.pk)
        assert "doc_type" in fs.forms[idx].errors


class TestStandaloneIdentityDocForm:
    """独立证件管理页也必须拦非法类型，否则能绕过约束再造脏数据。"""

    def test_legal_client_with_id_card_rejected(self):
        client = _make_client(Client.LEGAL)
        form = ClientIdentityDocForm(data={"client": client.pk, "doc_type": ClientIdentityDoc.ID_CARD, "file_path": ""})
        assert not form.is_valid()
        assert "doc_type" in form.errors

    def test_legal_client_with_business_license_ok(self):
        client = _make_client(Client.LEGAL)
        form = ClientIdentityDocForm(
            data={"client": client.pk, "doc_type": ClientIdentityDoc.BUSINESS_LICENSE, "file_path": ""}
        )
        assert form.is_valid(), form.errors
