"""
创建默认提示词版本

为 AI 诉状生成系统创建默认的提示词版本.

Requirements: 6.2.1
"""

from apps.documents.models import PromptVersion
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help : str = "创建 AI 诉状生成的默认提示词版本"

    def handle(self, *args, **options) -> None:
        self.stdout.write("开始创建默认提示词版本...")

        # 定义默认提示词
        prompts = [
            {
                "name": "complaint",
                "version": "v1.0",
                "description": "起诉状生成提示词",
                "template": self._get_complaint_prompt(),
            },
            {
                "name": "defense",
                "version": "v1.0",
                "description": "答辩状生成提示词",
                "template": self._get_defense_prompt(),
            },
            {
                "name": "counterclaim",
                "version": "v1.0",
                "description": "反诉状生成提示词",
                "template": self._get_counterclaim_prompt(),
            },
            {
                "name": "counterclaim_defense",
                "version": "v1.0",
                "description": "反诉答辩状生成提示词",
                "template": self._get_counterclaim_defense_prompt(),
            },
        ]

        created_count = 0
        updated_count = 0

        for prompt_data in prompts:
            # 检查是否已存在
            existing = PromptVersion.objects.filter(name=prompt_data["name"], version=prompt_data["version"]).first()

            if existing:
                # 更新现有版本
                existing.template = prompt_data["template"]
                existing.description = prompt_data["description"]
                existing.is_active = True
                existing.save()
                updated_count += 1
                self.stdout.write(self.style.WARNING(f"更新提示词版本: {prompt_data['name']} {prompt_data['version']}"))
            else:
                # 创建新版本
                # 先将同名的其他版本设为非激活
                PromptVersion.objects.filter(name=prompt_data["name"]).update(is_active=False)

                # 创建新版本
                PromptVersion.objects.create(
                    name=prompt_data["name"],
                    version=prompt_data["version"],
                    template=prompt_data["template"],
                    description=prompt_data["description"],
                    is_active=True,
                )
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"创建提示词版本: {prompt_data['name']} {prompt_data['version']}"))

        self.stdout.write(self.style.SUCCESS(f"\n完成!创建 {created_count} 个,更新 {updated_count} 个提示词版本."))

    def _get_complaint_prompt(self) -> str:
        """起诉状提示词"""
        return """你是一位专业的诉讼律师,擅长撰写起诉状.

任务:根据案件信息和证据材料,生成专业的诉讼请求和事实与理由.

要求:
1. 诉讼请求应当明确、具体、可执行,使用"判令"、"确认"等法律术语
2. 事实与理由应当逻辑清晰、证据充分,按时间顺序叙述
3. 语言应当规范、专业、符合法律文书要求
4. 每个诉讼请求应当单独成段,使用"一、""二、"编号
5. 事实与理由应当分段叙述,每段首行缩进2字符

输出格式:
诉讼请求:
[诉讼请求内容]

事实与理由:
[事实与理由内容]"""

    def _get_defense_prompt(self) -> str:
        """答辩状提示词"""
        return """你是一位专业的诉讼律师,擅长撰写答辩状.

任务:根据案件信息和证据材料,生成专业的答辩理由.

要求:
1. 答辩理由应当针对原告的诉讼请求逐一答辩
2. 应当充分利用证据材料支持答辩观点
3. 语言应当规范、专业、符合法律文书要求
4. 答辩理由应当分段叙述,每段首行缩进2字符

输出格式:
答辩理由:
[答辩理由内容]"""

    def _get_counterclaim_prompt(self) -> str:
        """反诉状提示词"""
        return """你是一位专业的诉讼律师,擅长撰写反诉状.

任务:根据案件信息和证据材料,生成专业的反诉请求和事实与理由.

要求:
1. 反诉请求应当明确、具体、可执行
2. 事实与理由应当逻辑清晰、证据充分
3. 语言应当规范、专业、符合法律文书要求
4. 每个反诉请求应当单独成段,使用"一、""二、"编号
5. 事实与理由应当分段叙述,每段首行缩进2字符

输出格式:
反诉请求:
[反诉请求内容]

事实与理由:
[事实与理由内容]"""

    def _get_counterclaim_defense_prompt(self) -> str:
        """反诉答辩状提示词"""
        return """你是一位专业的诉讼律师,擅长撰写反诉答辩状.

任务:根据案件信息和证据材料,生成专业的反诉答辩理由.

要求:
1. 反诉答辩理由应当针对对方的反诉请求逐一答辩
2. 应当充分利用证据材料支持答辩观点
3. 语言应当规范、专业、符合法律文书要求
4. 答辩理由应当分段叙述,每段首行缩进2字符

输出格式:
反诉答辩理由:
[反诉答辩理由内容]"""
