"""Business logic services."""

from typing import Any


class PipelineContextBuilder:
    def build_contract_context(self, contract: Any, split_fee: bool = True) -> dict[str, Any]:
        from apps.documents.services.placeholders import EnhancedContextBuilder
        from apps.documents.services.placeholders.types import PlaceholderContextData

        context_builder = EnhancedContextBuilder()
        context_data: PlaceholderContextData = {"contract": contract, "split_fee": split_fee}
        return context_builder.build_context(context_data)

    def build_supplementary_agreement_context(
        self,
        *,
        contract: Any,
        supplementary_agreement: Any,
        agreement_principals: Any,
        contract_principals: Any,
        agreement_opposing: Any,
    ) -> dict[str, Any]:
        from apps.documents.services.placeholders.context_builder import EnhancedContextBuilder
        from apps.documents.services.placeholders.types import PlaceholderContextData

        context_builder = EnhancedContextBuilder()
        context_data: PlaceholderContextData = {
            "contract": contract,
            "supplementary_agreement": supplementary_agreement,
            "agreement_principals": agreement_principals,
            "contract_principals": contract_principals,
            "agreement_opposing": agreement_opposing,
        }
        return context_builder.build_context(context_data)

    def build_archive_context(self, contract: Any, case: Any = None) -> dict[str, Any]:
        """
        构建归档文书上下文。

        Args:
            contract: 合同实例
            case: 案件实例（可选，用于填充案件相关占位符）

        Returns:
            包含归档占位符的上下文字典
        """
        from apps.documents.services.placeholders.context_builder import EnhancedContextBuilder
        from apps.documents.services.placeholders.types import PlaceholderContextData

        context_builder = EnhancedContextBuilder()
        context_data: PlaceholderContextData = {
            "contract": contract,
            "case": case,
        }
        return context_builder.build_context(context_data)
