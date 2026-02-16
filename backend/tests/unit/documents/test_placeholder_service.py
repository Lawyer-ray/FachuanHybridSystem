import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.documents.models import Placeholder
from apps.documents.services.placeholder_service import PlaceholderService


@pytest.fixture
def service():
    return PlaceholderService()


def test_create_placeholder_success(db, service):
    placeholder = service.create_placeholder(
        key="case_name",
        display_name="案件名称",
        example_value="张三诉李四案",
        description="案件名称",
        is_active=True,
    )
    assert placeholder.key == "case_name"
    assert placeholder.display_name == "案件名称"
    assert placeholder.example_value == "张三诉李四案"
    assert placeholder.description == "案件名称"
    assert placeholder.is_active is True


def test_create_placeholder_requires_key_and_display_name(db, service):
    with pytest.raises(ValidationException):
        service.create_placeholder(key="", display_name="名称")
    with pytest.raises(ValidationException):
        service.create_placeholder(key="case_name", display_name="")


def test_create_placeholder_duplicate_key(db, service):
    Placeholder.objects.create(key="case_name", display_name="案件名称", is_active=True)
    with pytest.raises(ValidationException):
        service.create_placeholder(key="case_name", display_name="重复")


def test_get_placeholder_by_id_not_found(db, service):
    with pytest.raises(NotFoundError):
        service.get_placeholder_by_id(999999)


def test_get_placeholder_by_key_not_found(db, service):
    with pytest.raises(NotFoundError):
        service.get_placeholder_by_key("not_exist")


def test_update_placeholder_success(db, service):
    placeholder = Placeholder.objects.create(key="case_name", display_name="案件名称", is_active=True)
    updated = service.update_placeholder(
        placeholder_id=placeholder.id,
        display_name="案件标题",
        example_value="示例",
        description="说明",
        is_active=False,
    )
    assert updated.id == placeholder.id
    assert updated.key == "case_name"
    assert updated.display_name == "案件标题"
    assert updated.example_value == "示例"
    assert updated.description == "说明"
    assert updated.is_active is False


def test_delete_placeholder_soft_delete(db, service):
    placeholder = Placeholder.objects.create(key="case_name", display_name="案件名称", is_active=True)
    service.delete_placeholder(placeholder.id)
    placeholder.refresh_from_db()
    assert placeholder.is_active is False


def test_list_placeholders_default_only_active(db, service):
    Placeholder.objects.create(key="a", display_name="A", is_active=True)
    Placeholder.objects.create(key="b", display_name="B", is_active=False)
    result = service.list_placeholders()
    assert [p.key for p in result] == ["a"]


def test_get_placeholder_mapping_only_active(db, service):
    Placeholder.objects.create(key="a", display_name="A", is_active=True)
    Placeholder.objects.create(key="b", display_name="B", is_active=False)
    mapping = service.get_placeholder_mapping()
    assert set(mapping.keys()) == {"a"}


def test_bulk_update_placeholders(db, service):
    Placeholder.objects.create(key="a", display_name="A", is_active=True)
    Placeholder.objects.create(key="b", display_name="B", is_active=True)
    updated = service.bulk_update_placeholders(
        [
            {"key": "a", "display_name": "A2", "description": "d1"},
            {"key": "b", "is_active": False},
            {"key": "missing", "display_name": "X"},
        ]
    )
    assert updated == 2
    assert Placeholder.objects.get(key="a").display_name == "A2"
    assert Placeholder.objects.get(key="a").description == "d1"
    assert Placeholder.objects.get(key="b").is_active is False
