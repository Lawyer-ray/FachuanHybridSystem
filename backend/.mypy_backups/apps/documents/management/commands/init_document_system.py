"""
初始化文书生成系统配置

创建示例替换词数据.

Usage:
    python manage.py init_document_system
    python manage.py init_document_system --with-samples
"""
from apps.core.path import Path
from apps.documents.models import Placeholder
from django.conf import settings
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help: str = '初始化文书生成系统配置'

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument('--with-samples', action='store_true', help='创建示例替换词')
        parser.add_argument('--force', action='store_true', help='强制覆盖已存在的配置')

    def handle(self, *args, **options) -> None:
        with_samples = options['with_samples']
        force = options['force']
        self.stdout.write('初始化文书生成系统...')
        self._create_template_directories()
        if with_samples:
            self._create_sample_placeholders(force)
        self.stdout.write(self.style.SUCCESS('文书生成系统初始化完成!'))

    def _create_template_directories(self) -> None:
        """创建模板存储目录"""
        directories = [Path(settings.MEDIA_ROOT) / 'document_templates', Path(settings.MEDIA_ROOT) / 'document_templates' / 'versions', Path(settings.MEDIA_ROOT) / 'generated_documents']
        for directory in directories:
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                self.stdout.write(f'  创建目录: {directory}')
            else:
                self.stdout.write(f'  目录已存在: {directory}')

    def _create_sample_placeholders(self, force: bool) -> None:
        """创建示例替换词"""
        sample_placeholders = [{'key': 'case_name', 'display_name': '案件名称', 'example_value': '张三诉李四合同纠纷案', 'description': '案件的完整名称'}, {'key': 'case_number', 'display_name': '案号', 'example_value': '(2024)京0101民初12345号', 'description': '法院分配的案件编号'}, {'key': 'case_type', 'display_name': '案件类型', 'example_value': '民事纠纷', 'description': '案件类型(民事、刑事等)'}, {'key': 'filing_date', 'display_name': '立案日期', 'example_value': '2024年1月15日', 'description': '案件立案日期'}, {'key': 'plaintiff_name', 'display_name': '原告姓名', 'example_value': '张三', 'description': '原告的姓名或名称'}, {'key': 'plaintiff_id_number', 'display_name': '原告身份证号', 'example_value': '110101199001011234', 'description': '原告的身份证号码'}, {'key': 'defendant_name', 'display_name': '被告姓名', 'example_value': '李四', 'description': '被告的姓名或名称'}, {'key': 'contract_amount', 'display_name': '合同金额', 'example_value': '¥100,000.00', 'description': '合同总金额'}, {'key': 'contract_date', 'display_name': '合同签订日期', 'example_value': '2023年12月1日', 'description': '合同签订日期'}, {'key': 'lawyer_name', 'display_name': '代理律师', 'example_value': '王律师', 'description': '代理律师姓名'}, {'key': 'law_firm_name', 'display_name': '律师事务所', 'example_value': '北京某某律师事务所', 'description': '律师事务所名称'}, {'key': 'court_name', 'display_name': '法院名称', 'example_value': '北京市东城区人民法院', 'description': '受理法院名称'}, {'key': 'current_date', 'display_name': '当前日期', 'example_value': '2024年1月1日', 'description': '文书生成时的当前日期'}]
        created_count = 0
        updated_count = 0
        for placeholder_data in sample_placeholders:
            placeholder, created = Placeholder.objects.get_or_create(key=placeholder_data['key'], defaults={'display_name': placeholder_data['display_name'], 'example_value': placeholder_data.get('example_value', ''), 'description': placeholder_data.get('description', '')})
            if created:
                created_count += 1
                self.stdout.write(f'  创建替换词: {placeholder.key}')
            elif force:
                for field, value in placeholder_data.items():
                    if field != 'key':
                        setattr(placeholder, field, value)
                placeholder.save()
                updated_count += 1
                self.stdout.write(f'  更新替换词: {placeholder.key}')
            else:
                self.stdout.write(f'  跳过已存在: {placeholder.key}')
        self.stdout.write(f'示例替换词: 创建 {created_count} 个, 更新 {updated_count} 个')