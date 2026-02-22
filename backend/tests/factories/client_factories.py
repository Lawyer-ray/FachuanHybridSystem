"""
客户模块 Factory 类
"""

import factory
from factory.django import DjangoModelFactory

from apps.client.models import Client, ClientIdentityDoc


class ClientFactory(DjangoModelFactory):
    """客户 Factory"""

    class Meta:
        model = Client

    name = factory.Sequence(lambda n: f"客户{n}")
    phone = factory.Sequence(lambda n: f"138{n:08d}")
    address = factory.Faker("address", locale="zh_CN")
    client_type = Client.NATURAL
    id_number = factory.Sequence(lambda n: f"110101199001{n:06d}")
    legal_representative = ""
    is_our_client = True


class LegalClientFactory(ClientFactory):
    """法人客户 Factory"""

    client_type = Client.LEGAL
    legal_representative = factory.Faker("name", locale="zh_CN") # type: ignore[assignment]
    id_number = factory.Sequence(lambda n: f"91110000{n:010d}")


class ClientIdentityDocFactory(DjangoModelFactory):
    """客户证件文档 Factory"""

    class Meta:
        model = ClientIdentityDoc

    client = factory.SubFactory(ClientFactory)
    doc_type = ClientIdentityDoc.ID_CARD
    file_path = factory.Faker("file_path")
