"""Client App Schemas。

按子域拆分：``client_schemas`` / ``identity_doc_schemas`` / ``enterprise_schemas``
/ ``property_clue_schemas`` / ``related_items_schemas``。本 ``__init__`` 重导出全部
Schema，保持 ``apps.client.schemas`` 的导入面不变。
"""

from __future__ import annotations

from .client_schemas import (
    ClientIn,
    ClientOut,
    ClientUpdateIn,
    IdCardValidateIn,
    IdCardValidateOut,
    OACredentialCheckOut,
    ParseTextIn,
    PartyListOut,
)
from .enterprise_schemas import (
    EnterpriseClientPrefillDataOut,
    EnterpriseClientPrefillOut,
    EnterpriseCompanyCandidateOut,
    EnterpriseCompanyProfileOut,
    EnterpriseCompanySearchOut,
    EnterpriseDuplicateClientOut,
)
from .identity_doc_schemas import (
    BindMergedDocIn,
    ClientIdentityDocOut,
    IdentityDocDetailOut,
    IdentityRecognizeOut,
    MergeIdCardManualIn,
)
from .property_clue_schemas import (
    ContentTemplateOut,
    PropertyClueAttachmentOut,
    PropertyClueIn,
    PropertyClueOut,
    PropertyClueUpdateIn,
)
from .related_items_schemas import RelatedCaseOut, RelatedContractOut, RelatedItemsOut

__all__ = [
    "BindMergedDocIn",
    "ClientIdentityDocOut",
    "ClientIn",
    "ClientOut",
    "ClientUpdateIn",
    "ContentTemplateOut",
    "EnterpriseClientPrefillDataOut",
    "EnterpriseClientPrefillOut",
    "EnterpriseCompanyCandidateOut",
    "EnterpriseCompanyProfileOut",
    "EnterpriseCompanySearchOut",
    "EnterpriseDuplicateClientOut",
    "IdCardValidateIn",
    "IdCardValidateOut",
    "IdentityDocDetailOut",
    "IdentityRecognizeOut",
    "MergeIdCardManualIn",
    "OACredentialCheckOut",
    "ParseTextIn",
    "PartyListOut",
    "PropertyClueAttachmentOut",
    "PropertyClueIn",
    "PropertyClueOut",
    "PropertyClueUpdateIn",
    "RelatedCaseOut",
    "RelatedContractOut",
    "RelatedItemsOut",
]
