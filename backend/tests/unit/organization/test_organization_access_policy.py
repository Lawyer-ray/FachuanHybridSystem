import pytest

from apps.core.exceptions import ForbiddenError
from apps.organization.services.organization_access_policy import OrganizationAccessPolicy


class _Obj:
    def __init__(self, **attrs):
        for k, v in attrs.items():
            setattr(self, k, v)


class TestOrganizationAccessPolicy:
    def setup_method(self):
        self.policy = OrganizationAccessPolicy()

    def test_ensure_authenticated_requires_authenticated_user(self):
        with pytest.raises(ForbiddenError):
            self.policy.ensure_authenticated(None)

        user = _Obj(is_authenticated=False)
        with pytest.raises(ForbiddenError):
            self.policy.ensure_authenticated(user)

        user = _Obj(is_authenticated=True)
        self.policy.ensure_authenticated(user)

    def test_can_create_requires_admin_or_superuser(self):
        user = _Obj(is_authenticated=True, is_admin=False, is_superuser=False)
        assert self.policy.can_create(user) is False

        admin = _Obj(is_authenticated=True, is_admin=True, is_superuser=False)
        assert self.policy.can_create(admin) is True

        superuser = _Obj(is_authenticated=True, is_admin=False, is_superuser=True)
        assert self.policy.can_create(superuser) is True

    def test_ensure_can_create_raises(self):
        user = _Obj(is_authenticated=True, is_admin=False, is_superuser=False)
        with pytest.raises(ForbiddenError):
            self.policy.ensure_can_create(user)

        admin = _Obj(is_authenticated=True, is_admin=True, is_superuser=False)
        self.policy.ensure_can_create(admin)

    def test_can_read_lawyer_requires_same_law_firm_or_superuser(self):
        lawyer = _Obj(law_firm_id=10)

        anon = _Obj(is_authenticated=False, is_superuser=False, law_firm_id=10)
        assert self.policy.can_read_lawyer(anon, lawyer) is False

        same_firm_user = _Obj(is_authenticated=True, is_superuser=False, law_firm_id=10)
        assert self.policy.can_read_lawyer(same_firm_user, lawyer) is True

        other_firm_user = _Obj(is_authenticated=True, is_superuser=False, law_firm_id=11)
        assert self.policy.can_read_lawyer(other_firm_user, lawyer) is False

        superuser = _Obj(is_authenticated=True, is_superuser=True, law_firm_id=11)
        assert self.policy.can_read_lawyer(superuser, lawyer) is True

        with pytest.raises(ForbiddenError):
            self.policy.ensure_can_read_lawyer(user=other_firm_user, lawyer=lawyer)

    def test_can_update_lawyer_allows_self_or_admin_same_firm_or_superuser(self):
        lawyer = _Obj(id=3, law_firm_id=10)

        assert self.policy.can_update_lawyer(None, lawyer) is False

        other = _Obj(is_authenticated=True, is_superuser=False, is_admin=False, id=4, law_firm_id=10)
        assert self.policy.can_update_lawyer(other, lawyer) is False

        self_user = _Obj(is_authenticated=True, is_superuser=False, is_admin=False, id=3, law_firm_id=11)
        assert self.policy.can_update_lawyer(self_user, lawyer) is True

        admin_same_firm = _Obj(is_authenticated=True, is_superuser=False, is_admin=True, id=4, law_firm_id=10)
        assert self.policy.can_update_lawyer(admin_same_firm, lawyer) is True

        admin_other_firm = _Obj(is_authenticated=True, is_superuser=False, is_admin=True, id=4, law_firm_id=11)
        assert self.policy.can_update_lawyer(admin_other_firm, lawyer) is False

        superuser = _Obj(is_authenticated=True, is_superuser=True, is_admin=False, id=4, law_firm_id=11)
        assert self.policy.can_update_lawyer(superuser, lawyer) is True

        self.policy.ensure_can_update_lawyer(user=self_user, lawyer=lawyer)
        self.policy.ensure_can_update_lawyer(user=admin_same_firm, lawyer=lawyer)
        self.policy.ensure_can_update_lawyer(user=superuser, lawyer=lawyer)

    def test_ensure_can_update_lawyer_raises(self):
        lawyer = _Obj(id=3, law_firm_id=10)
        user = _Obj(is_authenticated=True, is_superuser=False, is_admin=False, id=4, law_firm_id=10)
        with pytest.raises(ForbiddenError):
            self.policy.ensure_can_update_lawyer(user, lawyer)

    def test_can_delete_lawyer_requires_admin_same_firm_or_superuser(self):
        lawyer = _Obj(id=3, law_firm_id=10)

        assert self.policy.can_delete_lawyer(None, lawyer) is False

        user = _Obj(is_authenticated=True, is_superuser=False, is_admin=False, id=4, law_firm_id=10)
        assert self.policy.can_delete_lawyer(user, lawyer) is False
        with pytest.raises(ForbiddenError):
            self.policy.ensure_can_delete_lawyer(user, lawyer)

        admin_other_firm = _Obj(is_authenticated=True, is_superuser=False, is_admin=True, id=4, law_firm_id=11)
        assert self.policy.can_delete_lawyer(admin_other_firm, lawyer) is False

        admin_same_firm = _Obj(is_authenticated=True, is_superuser=False, is_admin=True, id=4, law_firm_id=10)
        assert self.policy.can_delete_lawyer(admin_same_firm, lawyer) is True
        self.policy.ensure_can_delete_lawyer(admin_same_firm, lawyer)

        superuser = _Obj(is_authenticated=True, is_superuser=True, is_admin=False, id=4, law_firm_id=11)
        assert self.policy.can_delete_lawyer(superuser, lawyer) is True

    def test_lawfirm_permissions(self):
        lawfirm = _Obj(id=10)

        assert self.policy.can_read_lawfirm(None, lawfirm) is False
        assert self.policy.can_update_lawfirm(None, lawfirm) is False
        assert self.policy.can_delete_lawfirm(None, lawfirm) is False

        user = _Obj(is_authenticated=True, is_superuser=False, is_admin=False, law_firm_id=10)
        assert self.policy.can_read_lawfirm(user, lawfirm) is True
        self.policy.ensure_can_read_lawfirm(user, lawfirm)
        assert self.policy.can_update_lawfirm(user, lawfirm) is False
        with pytest.raises(ForbiddenError):
            self.policy.ensure_can_update_lawfirm(user, lawfirm)

        admin_same = _Obj(is_authenticated=True, is_superuser=False, is_admin=True, law_firm_id=10)
        assert self.policy.can_update_lawfirm(admin_same, lawfirm) is True
        self.policy.ensure_can_update_lawfirm(admin_same, lawfirm)
        assert self.policy.can_delete_lawfirm(admin_same, lawfirm) is False
        with pytest.raises(ForbiddenError):
            self.policy.ensure_can_delete_lawfirm(admin_same, lawfirm)

        superuser = _Obj(is_authenticated=True, is_superuser=True, is_admin=False, law_firm_id=11)
        assert self.policy.can_read_lawfirm(superuser, lawfirm) is True
        assert self.policy.can_update_lawfirm(superuser, lawfirm) is True
        assert self.policy.can_delete_lawfirm(superuser, lawfirm) is True
        self.policy.ensure_can_delete_lawfirm(superuser, lawfirm)

        other = _Obj(is_authenticated=True, is_superuser=False, is_admin=True, law_firm_id=11)
        assert self.policy.can_read_lawfirm(other, lawfirm) is False
        with pytest.raises(ForbiddenError):
            self.policy.ensure_can_read_lawfirm(other, lawfirm)

    def test_team_permissions(self):
        team = _Obj(law_firm_id=10)

        user = _Obj(is_authenticated=True, is_superuser=False, is_admin=False, law_firm_id=10)
        assert self.policy.can_read_team(user, team) is True
        self.policy.ensure_can_read_team(user, team)
        assert self.policy.can_update_team(user, team) is False
        with pytest.raises(ForbiddenError):
            self.policy.ensure_can_update_team(user, team)
        assert self.policy.can_delete_team(user, team) is False
        with pytest.raises(ForbiddenError):
            self.policy.ensure_can_delete_team(user, team)

        admin_same = _Obj(is_authenticated=True, is_superuser=False, is_admin=True, law_firm_id=10)
        assert self.policy.can_update_team(admin_same, team) is True
        self.policy.ensure_can_update_team(admin_same, team)
        assert self.policy.can_delete_team(admin_same, team) is True
        self.policy.ensure_can_delete_team(admin_same, team)

        superuser = _Obj(is_authenticated=True, is_superuser=True, is_admin=False, law_firm_id=11)
        assert self.policy.can_read_team(superuser, team) is True
        assert self.policy.can_update_team(superuser, team) is True
        assert self.policy.can_delete_team(superuser, team) is True

        other = _Obj(is_authenticated=True, is_superuser=False, is_admin=True, law_firm_id=11)
        assert self.policy.can_read_team(other, team) is False
        with pytest.raises(ForbiddenError):
            self.policy.ensure_can_read_team(user=other, team=team)
