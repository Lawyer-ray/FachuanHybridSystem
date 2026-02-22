"""
PromptTemplate Repository

封装 PromptTemplate 模型的数据访问操作
"""

from apps.core.models.prompt_template import PromptTemplate


class PromptTemplateRepository:
    """Prompt 模板数据访问层"""

    def create(
        self,
        name: str,
        title: str,
        template: str,
        description: str = "",
        category: str = "general",
        is_active: bool = True,
        version: str = "1.0",
    ) -> PromptTemplate:
        """创建模板"""
        return PromptTemplate.objects.create(
            name=name,
            title=title,
            template=template,
            description=description,
            category=category,
            is_active=is_active,
            version=version,
        )

    def get_by_id(self, template_id: int) -> PromptTemplate | None:
        """根据 ID 获取模板"""
        return PromptTemplate.objects.filter(id=template_id).first()

    def get_by_name(self, name: str) -> PromptTemplate | None:
        """根据名称获取模板"""
        return PromptTemplate.objects.filter(name=name).first()

    def get_all_active(self) -> list[PromptTemplate]:
        """获取所有启用的模板"""
        return list(PromptTemplate.objects.filter(is_active=True))

    def delete(self, template_id: int) -> tuple[int, dict[str, int]]:
        """删除模板"""
        return PromptTemplate.objects.filter(id=template_id).delete()
