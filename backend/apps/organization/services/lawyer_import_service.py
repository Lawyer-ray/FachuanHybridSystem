from __future__ import annotations

import logging
import secrets
from typing import Any, cast

from apps.organization.models import AccountCredential, LawFirm, Lawyer, Team
from apps.organization.models.team import TeamType

logger = logging.getLogger("apps.organization")


def get_or_create_law_firm(name: str) -> tuple[LawFirm, bool]:
    """按名称取/建律所，并发安全。

    `name` 已加 unique=True：两个进程同时 get_or_create 同名律所时，后插入的一方
    会撞唯一约束抛 IntegrityError（get_or_create 只在"自己插入失败后重查"的窗口内
    兜底，事务隔离级别下仍可能冒泡）。这里显式捕获并重查，把并发从报错降级为
    "拿到对端刚建好的那一行"。
    """
    from django.db import IntegrityError, transaction

    try:
        with transaction.atomic():
            return LawFirm.objects.get_or_create(name=name)
    except IntegrityError:
        # 唯一约束冲突 = 另一端已插入同名律所，直接取回来
        return LawFirm.objects.get(name=name), False


class LawyerImportService:
    """Handle JSON import business rules for Lawyer admin import."""

    def import_from_json(
        self,
        data_list: list[dict[str, Any]],
        *,
        actor: str,
    ) -> tuple[int, int, list[str]]:
        success = skipped = 0
        errors: list[str] = []

        for i, item in enumerate(data_list, 1):
            username = item.get("username", "")
            try:
                existing = Lawyer.objects.filter(username=username).first()
                if existing:
                    self._update_existing_lawyer(existing=existing, item=item)
                    success += 1
                    continue

                self._create_lawyer(item=item)
                success += 1
            except Exception as exc:
                logger.exception("导入律师失败", extra={"index": i, "username": username, "actor": actor})
                errors.append(f"[{i}] {username} ({type(exc).__name__}): {exc}")

        return success, skipped, errors

    def _update_existing_lawyer(self, *, existing: Lawyer, item: dict[str, Any]) -> None:
        update_fields: list[str] = []
        for field, json_key in [
            ("real_name", "real_name"),
            ("phone", "phone"),
            ("license_no", "license_no"),
            ("id_card", "id_card"),
        ]:
            if not getattr(existing, field) and item.get(json_key):
                setattr(existing, field, item[json_key])
                update_fields.append(field)

        if not existing.license_pdf and item.get("license_pdf"):
            existing.license_pdf = item["license_pdf"]
            update_fields.append("license_pdf")

        if not existing.law_firm and item.get("law_firm"):
            existing.law_firm, _ = get_or_create_law_firm(item["law_firm"])
            update_fields.append("law_firm")

        if update_fields:
            existing.save(update_fields=update_fields)

        self._merge_lawyer_teams(existing=existing, item=item)
        self._merge_biz_teams(existing=existing, item=item)
        self._merge_credentials(existing=existing, item=item)

    def _create_lawyer(self, *, item: dict[str, Any]) -> Lawyer:
        law_firm: LawFirm | None = None
        if item.get("law_firm"):
            law_firm, _ = get_or_create_law_firm(item["law_firm"])

        password = item.get("password") or secrets.token_urlsafe(16)
        lawyer = cast(
            Lawyer,
            Lawyer.objects.create_user(
                username=item.get("username", ""),
                password=password,
                real_name=item.get("real_name", ""),
                phone=item.get("phone") or None,
                license_no=item.get("license_no", ""),
                id_card=item.get("id_card", ""),
                is_admin=item.get("is_admin", False),
                is_active=item.get("is_active", False),
                is_staff=item.get("is_admin", False),
                law_firm=law_firm,
            ),
        )

        if item.get("license_pdf"):
            lawyer.license_pdf = item["license_pdf"]
            lawyer.save(update_fields=["license_pdf"])

        self._attach_lawyer_teams(lawyer=lawyer, item=item, law_firm=law_firm)
        self._attach_biz_teams(lawyer=lawyer, item=item, law_firm=law_firm)
        self._attach_credentials(lawyer=lawyer, item=item)

        return lawyer

    def _merge_lawyer_teams(self, *, existing: Lawyer, item: dict[str, Any]) -> None:
        if not item.get("lawyer_teams"):
            return
        existing_lt_names = set(existing.lawyer_teams.values_list("name", flat=True))
        for t in item["lawyer_teams"]:
            t_name = t if isinstance(t, str) else t.get("name", "")
            if t_name in existing_lt_names:
                continue
            t_firm_name = None if isinstance(t, str) else t.get("law_firm")
            t_firm = get_or_create_law_firm(t_firm_name)[0] if t_firm_name else existing.law_firm
            # 查找键必须含 law_firm：Team 有 (law_firm, team_type, name) 唯一约束，
            # 缺失会跨律所误命中或创建出违反约束的重复团队
            team, _ = Team.objects.get_or_create(name=t_name, team_type=TeamType.LAWYER, law_firm=cast(LawFirm, t_firm))
            existing.lawyer_teams.add(team)

    def _merge_biz_teams(self, *, existing: Lawyer, item: dict[str, Any]) -> None:
        if not item.get("biz_teams"):
            return
        existing_bt_names = set(existing.biz_teams.values_list("name", flat=True))
        for t_name in item["biz_teams"]:
            if t_name in existing_bt_names:
                continue
            team, _ = Team.objects.get_or_create(
                name=t_name,
                team_type=TeamType.BIZ,
                law_firm=cast(LawFirm, existing.law_firm),
            )
            existing.biz_teams.add(team)

    def _merge_credentials(self, *, existing: Lawyer, item: dict[str, Any]) -> None:  # pragma: no cover
        if not item.get("credentials"):
            return
        existing_sites = set(existing.credentials.values_list("site_name", flat=True))
        for cred in item["credentials"]:
            if cred.get("site_name") in existing_sites:
                continue
            AccountCredential.objects.create(
                lawyer=existing,
                site_name=cred.get("site_name", ""),
                url=cred.get("url", ""),
                account=cred.get("account", ""),
                password=cred.get("password", ""),
            )

    def _attach_lawyer_teams(
        self, *, lawyer: Lawyer, item: dict[str, Any], law_firm: LawFirm | None
    ) -> None:  # pragma: no cover
        if not item.get("lawyer_teams"):
            return
        lawyer_team_objs: list[Team] = []
        for t in item["lawyer_teams"]:
            t_name = t if isinstance(t, str) else t.get("name", "")
            t_firm_name = None if isinstance(t, str) else t.get("law_firm")
            t_firm = get_or_create_law_firm(t_firm_name)[0] if t_firm_name else law_firm
            # 查找键必须含 law_firm，理由同 _merge_lawyer_teams
            team, _ = Team.objects.get_or_create(
                name=t_name,
                team_type=TeamType.LAWYER,
                law_firm=cast(LawFirm, t_firm),
            )
            lawyer_team_objs.append(team)
        lawyer.lawyer_teams.set(lawyer_team_objs)

    def _attach_biz_teams(
        self, *, lawyer: Lawyer, item: dict[str, Any], law_firm: LawFirm | None
    ) -> None:  # pragma: no cover
        if not item.get("biz_teams"):
            return
        biz_team_objs: list[Team] = []
        for t_name in item["biz_teams"]:
            team, _ = Team.objects.get_or_create(
                name=t_name,
                team_type=TeamType.BIZ,
                law_firm=cast(LawFirm, law_firm),
            )
            biz_team_objs.append(team)
        lawyer.biz_teams.set(biz_team_objs)

    def _attach_credentials(self, *, lawyer: Lawyer, item: dict[str, Any]) -> None:  # pragma: no cover
        for cred in item.get("credentials", []):
            AccountCredential.objects.create(
                lawyer=lawyer,
                site_name=cred.get("site_name", ""),
                url=cred.get("url", ""),
                account=cred.get("account", ""),
                password=cred.get("password", ""),
            )
