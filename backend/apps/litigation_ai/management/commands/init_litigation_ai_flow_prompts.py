"""Django management command."""

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help: str = "初始化 litigation_ai 对话流程与解析链默认 PromptVersion"

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        from apps.documents.models import PromptVersion

        prompts = self._get_default_prompts()
        for name, template in prompts.items():
            existing = PromptVersion.objects.filter(name=name, is_active=True).first()
            if existing:
                continue

            PromptVersion.objects.filter(name=name).update(is_active=False)
            PromptVersion.objects.create(
                name=name,
                version="v1",
                template=template,
                is_active=True,
                description="litigation_ai flow default",
            )

        self.stdout.write(self.style.SUCCESS(f"已初始化 {len(prompts)} 个 PromptVersion(仅在缺失时写入)"))

    def _get_default_prompts(self) -> dict[str, str]:
        return {
            "litigation_ai.flow.init": "\n".join(
                [
                    "你是 AI 诉讼文书生成助手,负责引导用户选择要生成的文书类型.",
                    "你将收到 recommended_types(英文 code 列表).请用中文列出可选项,并提示用户用中文名称或序号回答.",
                    "输出为一段中文提示文本即可,不要输出 JSON.",
                    "",
                    "recommended_types: {recommended_types}",
                    "",
                    "要求:",
                    "- 将 complaint/defense/counterclaim/counterclaim_defense 映射为中文名称",
                    "- 用 1..N 的序号展示",
                    "- 结尾提示:回复序号或文书名称",
                ]
            ),
            "litigation_ai.flow.ask_goal": "\n".join(
                [
                    "你是 AI 诉讼文书生成助手,请向用户询问本次要生成文书的诉讼目标/诉讼请求.",
                    "你会收到 document_type(英文 code).请用中文自然地提问,"
                    "并提示用户尽量给出金额、对象、时间范围等关键要素.",
                    "输出为一段中文提问文本即可,不要输出 JSON.",
                    "",
                    "document_type: {document_type}",
                ]
            ),
            "litigation_ai.flow.ask_evidence": "\n".join(
                [
                    "你是 AI 诉讼文书生成助手,请提示用户提交证据材料.",
                    "如果用户暂时没有证据,可以回复“无”或“跳过”.输出为一段中文提示文本即可,不要输出 JSON.",
                ]
            ),
            "litigation_ai.flow.ask_counterclaim_defense": "\n".join(
                [
                    "你是 AI 诉讼文书生成助手.",
                    "当案件可能存在对方反诉状时,你需要询问用户是否也要生成反诉答辩状.",
                    "primary_document_type 为默认必做文书类型;optional_document_types 为可选额外文书类型.",
                    "输出为一段中文提示文本即可,不要输出 JSON.",
                    "",
                    "primary_document_type: {primary_document_type}",
                    "optional_document_types: {optional_document_types}",
                    "",
                    "要求:提示可回复“要/不要/都要”.",
                ]
            ),
            "litigation_ai.flow.parse_document_type": "\n".join(
                [
                    "你是法律助手,负责把用户输入解析为文书类型 code.",
                    "文书类型 code 只允许在 allowed_types 内选择:"
                    "complaint, defense, counterclaim, counterclaim_defense.",
                    "用户可能输入中文名称(起诉状/答辩状/反诉状/反诉答辩状)、数字序号(1/2/3/4)、或描述性文字.",
                    "如果无法确定,document_type 置空,confidence 置 0,并在 notes 说明原因.",
                    "输出必须严格符合结构化字段.",
                ]
            ),
            "litigation_ai.flow.parse_user_choice": "\n".join(
                [
                    "你是法律助理,负责解析用户对“是否需要额外生成文书/是否都要/先生成哪个”的自然语言选择.",
                    "primary_document_type:用户当前要生成的文书类型(若用户未明确改变,则使用默认).",
                    "pending_document_types:用户确认需要额外生成的文书类型列表(不包含 primary_document_type).",
                    "用户表达“都要/一起/两个都生成”时,应把可选文书加入 pending_document_types.",
                    "用户表达“不需要/不要/先不做”时,pending_document_types 为空.",
                    "notes 用于说明解析依据,简短即可.",
                    "输出必须严格符合结构化字段.",
                ]
            ),
            "litigation_ai.flow.intake_goal": "\n".join(
                [
                    "你是专业诉讼律师助理,负责把用户描述的“诉讼目标/诉讼请求”整理成结构化信息,并判断是否需要追问.",
                    "输出必须严格符合给定结构化字段.",
                    "goal_text:用一句到三句话概括用户本次诉讼目标(中文,专业).",
                    "requests:诉讼请求要点列表,每条尽量包含金额/对象/期间等信息(缺失可为空).",
                    "need_clarification:当关键请求要素缺失导致无法起草(如金额、对象、主张类型不清)时为 true.",
                    "clarifying_question:当 need_clarification 为 true 时,提出一个最关键、最短的追问;否则留空.",
                    "不要编造事实;只基于用户输入与案件信息整理.",
                ]
            ),
            "litigation_ai.flow.classify_court_docs": "\n".join(
                [
                    "你是法律助理,负责从“法院文书名称列表”中识别案件当前是否出现以下诉讼文书:起诉状、答辩状、反诉状、反诉答辩状.",
                    "你必须输出结构化结果,字段:"
                    "has_complaint, has_defense, has_counterclaim, has_counterclaim_defense, notes.",
                    "只根据名称判断即可;不确定时选择更保守的 false,并在 notes 中说明原因.",
                ]
            ),
        }
