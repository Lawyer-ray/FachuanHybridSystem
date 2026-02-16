"""
Organization 模块的 Factory 类
"""
import factory
from factory.django import DjangoModelFactory
from apps.organization.models import LawFirm, Lawyer, Team, TeamType


class LawFirmFactory(DjangoModelFactory):
    """律所工厂"""
    
    class Meta:
        model = LawFirm
    
    name = factory.Sequence(lambda n: f"测试律所{n}")
    address = factory.Faker('address', locale='zh_CN')
    phone = factory.Sequence(lambda n: f"138{n:08d}")
    social_credit_code = factory.Sequence(lambda n: f"91{n:016d}")
    bank_name = factory.Faker('company', locale='zh_CN')
    bank_account = factory.Sequence(lambda n: f"6222{n:015d}")


class LawyerFactory(DjangoModelFactory):
    """律师工厂"""
    
    class Meta:
        model = Lawyer
    
    username = factory.Sequence(lambda n: f"lawyer{n}")
    real_name = factory.Faker('name', locale='zh_CN')
    phone = factory.Sequence(lambda n: f"139{n:08d}")
    license_no = factory.Sequence(lambda n: f"1{n:013d}")
    id_card = factory.Sequence(lambda n: f"44{n:016d}")
    law_firm = factory.SubFactory(LawFirmFactory)
    is_admin = False
    
    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        """设置密码"""
        if not create:
            return
        
        password = extracted or 'testpass123'
        obj.set_password(password)
        obj.save()


class TeamFactory(DjangoModelFactory):
    """团队工厂"""
    
    class Meta:
        model = Team
    
    name = factory.Sequence(lambda n: f"测试团队{n}")
    team_type = TeamType.LAWYER
    law_firm = factory.SubFactory(LawFirmFactory)
