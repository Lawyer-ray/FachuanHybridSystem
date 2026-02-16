"""Business logic services."""

from .types import ConversationStep


class FlowStateMachine:
    def parse_step(self, step_value: str | None) -> ConversationStep:
        if not step_value:
            return ConversationStep.INIT
        try:
            return ConversationStep(step_value)
        except ValueError:
            return ConversationStep.INIT

    def choose_primary_document_type(self, recommended_types: list[str] | None) -> str | None | None:
        if not recommended_types:
            return None
        priority = ["complaint", "defense", "counterclaim", "counterclaim_defense"]
        for t in priority:
            if t in recommended_types:
                return t
        return recommended_types[0]

    def need_doc_plan(self, primary_document_type: str | None, recommended_types: list[str] | None) -> bool:
        return bool(
            primary_document_type == "complaint"
            and "counterclaim_defense" in (recommended_types or [])
            and primary_document_type != "counterclaim_defense"
        )
