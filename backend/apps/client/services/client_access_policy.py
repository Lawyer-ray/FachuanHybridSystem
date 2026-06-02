"""当事人权限策略。"""

from typing import Any

from apps.core.security import DjangoPermsMixin


class ClientAccessPolicy(DjangoPermsMixin):
    def can_create_client(self, user: Any | None) -> bool:
        return bool(self.has_perm(user, "client.add_client"))

    def ensure_can_create_client(self, user: Any | None) -> None:
        self.ensure_has_perm(user, "client.add_client", "无权限创建客户")

    def can_update_client(self, user: Any | None) -> bool:
        return bool(self.has_perm(user, "client.change_client"))

    def ensure_can_update_client(self, user: Any | None) -> None:
        self.ensure_has_perm(user, "client.change_client", "无权限更新该客户")

    def can_delete_client(self, user: Any | None) -> bool:
        return bool(self.has_perm(user, "client.delete_client"))

    def ensure_can_delete_client(self, user: Any | None) -> None:
        self.ensure_has_perm(user, "client.delete_client", "无权限删除该客户")
