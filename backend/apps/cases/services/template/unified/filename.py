"""Business logic services."""

import re
from dataclasses import dataclass
from typing import Protocol

from django.utils import timezone


class DateProvider(Protocol):
    def today_yyyymmdd(self) -> str: ...


class DjangoLocalDateProvider:
    def today_yyyymmdd(self) -> str:
        return timezone.localtime().strftime("%Y%m%d")


@dataclass(frozen=True)
class FilenameInputs:
    template_name: str
    case_name: str
    client_name: str | None
    function_code: str | None
    mode: str | None
    our_party_count: int


class FilenamePolicy:
    def __init__(self, *, date_provider: DateProvider | None = None) -> None:
        self.date_provider = date_provider or DjangoLocalDateProvider()

    def build(
        self,
        *,
        inputs: FilenameInputs,
        legal_rep_cert_code: str,
        power_of_attorney_code: str,
    ) -> str:
        date_str = self.date_provider.today_yyyymmdd()

        safe_template_name = self.safe_name(inputs.template_name or "模板")
        safe_case_name = self.safe_name(inputs.case_name or "案件")

        if inputs.function_code == legal_rep_cert_code and inputs.client_name:
            safe_client_name = self.safe_name(inputs.client_name)
            return f"{safe_template_name}（{safe_client_name}）V1_{date_str}.docx"

        if inputs.function_code == power_of_attorney_code:
            is_combined = inputs.mode == "combined"
            if not is_combined and inputs.our_party_count > 1 and inputs.client_name:
                safe_client_name = self.safe_name(inputs.client_name)
                return f"{safe_template_name}（{safe_client_name}）（{safe_case_name}）V1_{date_str}.docx"
            return f"{safe_template_name}（{safe_case_name}）V1_{date_str}.docx"

        return f"{safe_template_name}（{safe_case_name}）V1_{date_str}.docx"

    def safe_name(self, name: str) -> str:
        value = (name or "").strip()
        value = value.replace("/", "／").replace("\\", "＼")
        value = value.replace("\n", " ").replace("\r", " ").replace("\t", " ")
        value = re.sub(r"\s+", " ", value).strip()
        return value or "未命名"
