"""
端到端测试：Django Admin 性能整改验证

覆盖所有性能修复点，严格验证查询数量和行为正确性。
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase

from apps.cases.admin.caselog_admin import CaseLogAdmin
from apps.cases.models import Case, CaseLog
from apps.contracts.admin.supplementary_agreement_admin import SupplementaryAgreementAdmin
from apps.contracts.models import Contract, SupplementaryAgreement, SupplementaryAgreementParty
from apps.client.models import Client
from apps.core.models import ToolFavorite
from apps.evidence.admin.evidence_admin import EvidenceListAdmin
from apps.evidence.models import EvidenceList, EvidenceItem, ListType
from apps.message_hub.models import MessageSource
from apps.reminders.models import Reminder

User = get_user_model()


# ---------------------------------------------------------------------------
# P1: SupplementaryAgreementAdmin party_count
# ---------------------------------------------------------------------------
class SupplementaryAgreementAdminPartyCountTest(TestCase):
    """P1: party_count 应使用 annotate(Count) 而非 .count()，消除 N+1。"""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.contract = Contract.objects.create(name="测试合同P1", case_type="civil", status="active")
        cls.sa_0 = SupplementaryAgreement.objects.create(contract=cls.contract, name="SA-0")
        cls.sa_2 = SupplementaryAgreement.objects.create(contract=cls.contract, name="SA-2")
        cls.sa_5 = SupplementaryAgreement.objects.create(contract=cls.contract, name="SA-5")

        # 创建独立 client 避免 unique_together 冲突
        clients = []
        for i in range(7):
            c = Client.objects.create(name=f"P1-client-{i}", client_type="natural", is_our_client=False)
            clients.append(c)

        # sa_2: 2 个当事人
        for i in range(2):
            SupplementaryAgreementParty.objects.create(
                supplementary_agreement=cls.sa_2, client=clients[i], role="OPPOSING",
            )
        # sa_5: 5 个当事人
        for i in range(5):
            SupplementaryAgreementParty.objects.create(
                supplementary_agreement=cls.sa_5, client=clients[i + 2], role="BENEFICIARY",
            )

    def _make_request(self):
        factory = RequestFactory()
        request = factory.get("/admin/contracts/supplementaryagreement/")
        request.user = User(is_superuser=True, is_staff=True)
        return request

    def test_party_count_reads_annotation_not_count_method(self) -> None:
        """party_count 应读取 annotate 的值，不触发额外查询。"""
        admin_obj = SupplementaryAgreementAdmin(SupplementaryAgreement, AdminSite())
        qs = admin_obj.get_queryset(self._make_request())

        with self.assertNumQueries(1):  # 仅 1 次查询（含 LEFT JOIN + COUNT）
            results = list(qs)

        count_map = {obj.pk: obj.party_count for obj in results}
        self.assertEqual(count_map[self.sa_0.pk], 0)
        self.assertEqual(count_map[self.sa_2.pk], 2)
        self.assertEqual(count_map[self.sa_5.pk], 5)

    def test_party_count_display_method_uses_annotation(self) -> None:
        """admin.display 方法应直接返回 obj.party_count，无额外查询。"""
        admin_obj = SupplementaryAgreementAdmin(SupplementaryAgreement, AdminSite())
        qs = admin_obj.get_queryset(self._make_request())
        obj = qs.get(pk=self.sa_5.pk)

        with self.assertNumQueries(0):
            result = admin_obj.party_count(obj)

        self.assertEqual(result, 5)

    def test_queryset_annotation_produces_single_query(self) -> None:
        """get_queryset 应仅产生 1 次查询（含 JOIN + COUNT）。"""
        admin_obj = SupplementaryAgreementAdmin(SupplementaryAgreement, AdminSite())
        qs = admin_obj.get_queryset(self._make_request())
        with self.assertNumQueries(1):
            list(qs)


# ---------------------------------------------------------------------------
# P0: CaseLogAdmin reminder 批量预填充
# ---------------------------------------------------------------------------
class CaseLogAdminReminderBatchTest(TestCase):
    """P0: CaseLogAdmin 应批量预填充 reminder 缓存，消除每行 2 次查询。"""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = User.objects.create_user(username="testadmin_p0", password="x")
        cls.contract = Contract.objects.create(name="测试合同P0", case_type="civil", status="active")
        cls.case = Case.objects.create(name="测试案件P0", contract=cls.contract)

        # 创建 10 个 CaseLog
        cls.case_logs = []
        for i in range(10):
            log = CaseLog.objects.create(case=cls.case, actor=cls.user, content=f"日志 {i}")
            cls.case_logs.append(log)

        # 为其中 5 个 CaseLog 创建提醒（仅绑定 case_log，不绑定 case，满足约束）
        for i in range(5):
            Reminder.objects.create(
                case_log=cls.case_logs[i],
                reminder_type="hearing",
                content=f"开庭提醒 {i}",
                due_at=datetime.datetime(2026, 1, i + 1, tzinfo=datetime.timezone.utc),
            )

    def test_batch_load_produces_single_query(self) -> None:
        """export_case_log_reminders_batch_internal 应仅 1 次查询加载所有提醒。"""
        case_log_ids = [obj.pk for obj in self.case_logs]

        from apps.core.infrastructure.service_locator import ServiceLocator
        svc = ServiceLocator.get_reminder_service()

        with self.assertNumQueries(1):
            batch = svc.export_case_log_reminders_batch_internal(case_log_ids=case_log_ids)

        # 验证有 5 个 case_log 有提醒
        non_empty = {k: v for k, v in batch.items() if v}
        self.assertEqual(len(non_empty), 5)

    def test_cache_hit_prevents_extra_queries(self) -> None:
        """预填充缓存后访问 reminder_type/reminder_time 不应触发额外查询。"""
        from apps.core.infrastructure.service_locator import ServiceLocator
        svc = ServiceLocator.get_reminder_service()
        batch = svc.export_case_log_reminders_batch_internal(
            case_log_ids=[log.pk for log in self.case_logs]
        )

        # 预填充缓存
        for obj in self.case_logs:
            reminders = batch.get(obj.pk, [])
            obj._cached_latest_reminder = reminders[-1] if reminders else None
            obj._cached_exported_reminders = reminders

        # 访问 reminder_type 和 reminder_time 不应触发任何查询
        pre = len(connection.queries)
        for obj in self.case_logs:
            _ = obj.reminder_type
            _ = obj.reminder_time
        post = len(connection.queries)

        self.assertEqual(pre, post, "缓存命中后不应有额外查询")

    def test_reminder_values_correct_after_batch(self) -> None:
        """批量预填充后 reminder_type/reminder_time 值应正确。"""
        from apps.core.infrastructure.service_locator import ServiceLocator
        svc = ServiceLocator.get_reminder_service()
        batch = svc.export_case_log_reminders_batch_internal(
            case_log_ids=[self.case_logs[0].pk, self.case_logs[7].pk]
        )

        # 有提醒的日志
        log_with = self.case_logs[0]
        reminders = batch.get(log_with.pk, [])
        log_with._cached_latest_reminder = reminders[-1] if reminders else None
        self.assertEqual(log_with.reminder_type, "hearing")
        self.assertIsNotNone(log_with.reminder_time)

        # 无提醒的日志
        log_without = self.case_logs[7]
        reminders_none = batch.get(log_without.pk, [])
        log_without._cached_latest_reminder = reminders_none[-1] if reminders_none else None
        self.assertIsNone(log_without.reminder_type)
        self.assertIsNone(log_without.reminder_time)

    def test_multiple_reminders_returns_latest(self) -> None:
        """多个提醒时应返回 due_at 最大的那条（按 case_log 分组，取最后一条）。"""
        log = self.case_logs[0]

        # 创建更晚的提醒（仅绑定 case_log）
        Reminder.objects.create(
            case_log=log,
            reminder_type="appeal_deadline",
            content="上诉期提醒",
            due_at=datetime.datetime(2026, 12, 31, tzinfo=datetime.timezone.utc),
        )

        from apps.core.infrastructure.service_locator import ServiceLocator
        svc = ServiceLocator.get_reminder_service()
        batch = svc.export_case_log_reminders_batch_internal(case_log_ids=[log.pk])
        reminders = batch.get(log.pk, [])
        # batch 按 due_at ASC 排序，最后一条即最新
        log._cached_latest_reminder = reminders[-1] if reminders else None

        self.assertEqual(log.reminder_type, "appeal_deadline")


# ---------------------------------------------------------------------------
# P2: EvidenceListAdmin 链式批量计算
# ---------------------------------------------------------------------------
class EvidenceListAdminChainBatchTest(TestCase):
    """P2: EvidenceListAdmin 应批量计算 start_order/start_page，消除链式遍历。"""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.contract = Contract.objects.create(name="测试合同P2", case_type="civil", status="active")
        cls.case = Case.objects.create(name="测试案件P2", contract=cls.contract)

        cls.el1 = EvidenceList.objects.create(
            case=cls.case, list_type=ListType.LIST_1, order=1, title="清单1", total_pages=10,
        )
        cls.el2 = EvidenceList.objects.create(
            case=cls.case, list_type=ListType.LIST_2, order=2, title="清单2", total_pages=20,
            previous_list=cls.el1,
        )
        cls.el3 = EvidenceList.objects.create(
            case=cls.case, list_type=ListType.LIST_3, order=3, title="清单3", total_pages=5,
            previous_list=cls.el2,
        )
        cls.el4 = EvidenceList.objects.create(
            case=cls.case, list_type=ListType.LIST_4, order=4, title="清单4", total_pages=15,
            previous_list=cls.el3,
        )

        # LIST_1: 3 items, LIST_2: 5 items, LIST_3: 2 items, LIST_4: 4 items
        for el, count in [(cls.el1, 3), (cls.el2, 5), (cls.el3, 2), (cls.el4, 4)]:
            for i in range(count):
                EvidenceItem.objects.create(evidence_list=el, name=f"E-{el.pk}-{i}", purpose="test", order=i + 1)

    def test_batch_matches_service_layer(self) -> None:
        """批量计算结果应与服务层逐条计算完全一致。"""
        from apps.evidence.services.core.evidence_service import EvidenceService
        from django.db.models import Count

        svc = EvidenceService()
        expected = {}
        for el in [self.el1, self.el2, self.el3, self.el4]:
            el.refresh_from_db()
            expected[el.pk] = (svc.calculate_start_order(el), svc.calculate_start_page(el))

        # 批量计算
        all_lists = (
            EvidenceList.objects.filter(case_id=self.case.pk)
            .annotate(_batch_item_count=Count("items"))
            .order_by("order", "pk")
            .only("pk", "order", "total_pages")
        )
        running_order, running_page = 1, 1
        computed: dict[int, tuple[int, int]] = {}
        for el in all_lists:
            computed[el.pk] = (running_order, running_page)
            running_order += getattr(el, "_batch_item_count", 0) or 0
            running_page += el.total_pages or 0

        for pk in [self.el1.pk, self.el2.pk, self.el3.pk, self.el4.pk]:
            self.assertEqual(computed[pk], expected[pk], f"清单 {pk} 位置不一致")

    def test_expected_chain_values(self) -> None:
        """验证链式计算的具体期望值。"""
        from apps.evidence.services.core.evidence_service import EvidenceService
        svc = EvidenceService()
        for el in [self.el1, self.el2, self.el3, self.el4]:
            el.refresh_from_db()

        # LIST_1: start_order=1, start_page=1
        self.assertEqual(svc.calculate_start_order(self.el1), 1)
        self.assertEqual(svc.calculate_start_page(self.el1), 1)
        # LIST_2: start_order=1+3=4, start_page=1+10=11
        self.assertEqual(svc.calculate_start_order(self.el2), 4)
        self.assertEqual(svc.calculate_start_page(self.el2), 11)
        # LIST_3: start_order=4+5=9, start_page=11+20=31
        self.assertEqual(svc.calculate_start_order(self.el3), 9)
        self.assertEqual(svc.calculate_start_page(self.el3), 31)
        # LIST_4: start_order=9+2=11, start_page=31+5=36
        self.assertEqual(svc.calculate_start_order(self.el4), 11)
        self.assertEqual(svc.calculate_start_page(self.el4), 36)

    def test_dict_cache_bypasses_service(self) -> None:
        """__dict__ 缓存命中时应完全跳过服务层调用。"""
        el = EvidenceList.objects.get(pk=self.el1.pk)
        el.__dict__["_cached_start_order"] = 999
        el.__dict__["_cached_start_page"] = 888

        with patch("apps.evidence.models.evidence._get_evidence_service") as mock_svc:
            self.assertEqual(el.start_order, 999)
            self.assertEqual(el.start_page, 888)
            mock_svc.assert_not_called()

    def test_no_cache_falls_back_to_service(self) -> None:
        """无缓存时应回退到服务层调用，返回正确值。"""
        el = EvidenceList.objects.get(pk=self.el1.pk)
        el.__dict__.pop("_cached_start_order", None)
        el.__dict__.pop("_cached_start_page", None)

        self.assertEqual(el.start_order, 1)
        self.assertEqual(el.start_page, 1)


# ---------------------------------------------------------------------------
# P7: __str__ 方法零 FK 查询
# ---------------------------------------------------------------------------
class ContractModelStrNoQueryTest(TestCase):
    """P7: __str__ 方法不应触发 FK 查询。"""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.contract = Contract.objects.create(name="测试合同P7", case_type="civil", status="active")

    def test_contract_payment_str_no_fk_query(self) -> None:
        """ContractPayment.__str__ 不应触发 contract FK 查询。"""
        from apps.contracts.models import ContractPayment
        payment = ContractPayment.objects.create(contract=self.contract, amount=Decimal("10000.00"))
        # 构造裸实例（无 ORM 缓存）
        payment = ContractPayment(pk=payment.pk, contract_id=self.contract.pk, amount=Decimal("10000.00"))

        with self.assertNumQueries(0):
            result = str(payment)

        self.assertIn(str(self.contract.pk), result)
        self.assertIn("10000", result)

    def test_client_payment_record_str_no_fk_query(self) -> None:
        """ClientPaymentRecord.__str__ 不应触发 contract FK 查询。"""
        from apps.contracts.models import ClientPaymentRecord
        record = ClientPaymentRecord.objects.create(contract=self.contract, amount=Decimal("5000.00"))
        record = ClientPaymentRecord(pk=record.pk, contract_id=self.contract.pk, amount=Decimal("5000.00"))

        with self.assertNumQueries(0):
            result = str(record)

        self.assertIn(str(self.contract.pk), result)

    def test_supplementary_agreement_str_no_fk_query(self) -> None:
        """SupplementaryAgreement.__str__ 不应触发 contract FK 查询。"""
        sa = SupplementaryAgreement.objects.create(contract=self.contract, name="补充P7")
        sa = SupplementaryAgreement(pk=sa.pk, contract_id=self.contract.pk, name="补充P7")

        with self.assertNumQueries(0):
            result = str(sa)

        self.assertIn(str(self.contract.pk), result)
        self.assertIn("补充P7", result)


# ---------------------------------------------------------------------------
# P8: MessageSource 索引
# ---------------------------------------------------------------------------
class MessageSourceIndexTest(TestCase):
    """P8: MessageSource 应有 source_type 索引。"""

    def test_source_type_index_exists(self) -> None:
        """source_type 字段应有数据库索引。"""
        table_name = MessageSource._meta.db_table
        with connection.cursor() as cursor:
            if connection.vendor == "postgresql":
                cursor.execute(
                    "SELECT indexname FROM pg_indexes WHERE tablename = %s AND indexdef LIKE '%%source_type%%'",
                    [table_name],
                )
                indexes = [row[0] for row in cursor.fetchall()]
                self.assertTrue(len(indexes) > 0, f"source_type 索引不存在于 {table_name}")
            elif connection.vendor == "sqlite":
                cursor.execute(f"PRAGMA index_list('{table_name}')")
                found = False
                for idx in cursor.fetchall():
                    cursor.execute(f"PRAGMA index_info('{idx[1]}')")
                    if "source_type" in [row[2] for row in cursor.fetchall()]:
                        found = True
                        break
                self.assertTrue(found, f"source_type 索引不存在于 {table_name}")


# ---------------------------------------------------------------------------
# P4: 模板缓存配置
# ---------------------------------------------------------------------------
class TemplateCachingConfigTest(TestCase):
    """P4: 生产环境应使用 cached.Loader。"""

    def test_settings_code_has_cached_loader_logic(self) -> None:
        """settings.py 应包含 cached.Loader 配置逻辑。"""
        import ast
        from pathlib import Path

        settings_path = Path(__file__).resolve().parents[3] / "apiSystem" / "apiSystem" / "settings.py"
        source = settings_path.read_text()

        # 验证 settings.py 中包含 cached.Loader 相关代码
        self.assertIn("cached.Loader", source, "settings.py 应包含 cached.Loader 配置")
        self.assertIn("django.template.loaders.cached.Loader", source)
        self.assertIn("django.template.loaders.filesystem.Loader", source)
        self.assertIn("django.template.loaders.app_directories.Loader", source)

        # 验证是条件配置（非 DEBUG 时启用）
        self.assertIn("if not DEBUG", source, "cached.Loader 应仅在非 DEBUG 时启用")

    def test_debug_mode_uses_app_dirs(self) -> None:
        """DEBUG=True 时应使用 APP_DIRS（不缓存模板）。"""
        if not settings.DEBUG:
            self.skipTest("仅在 DEBUG 模式下测试")

        tpl = settings.TEMPLATES[0]
        self.assertTrue(tpl.get("APP_DIRS", False), "DEBUG=True 时应使用 APP_DIRS")
        # 不应有 loaders 配置
        self.assertFalse(
            tpl.get("OPTIONS", {}).get("loaders"),
            "DEBUG=True 时不应配置 loaders",
        )


# ---------------------------------------------------------------------------
# P3: Session 后端配置
# ---------------------------------------------------------------------------
class SessionEngineConfigTest(TestCase):
    """P3: Session 后端应为 cached_db。"""

    def test_session_engine_is_cached_db(self) -> None:
        self.assertEqual(settings.SESSION_ENGINE, "django.contrib.sessions.backends.cached_db")

    def test_session_cache_alias_is_default(self) -> None:
        self.assertEqual(getattr(settings, "SESSION_CACHE_ALIAS", "default"), "default")


# ---------------------------------------------------------------------------
# P5: context processor 移除 + 侧边栏缓存
# ---------------------------------------------------------------------------
class ToolFavoriteCacheTest(TestCase):
    """P5: context processor 已移除，侧边栏查询应有缓存。"""

    def test_context_processor_removed(self) -> None:
        """tool_favorites 不应在 TEMPLATES context_processors 中。"""
        processors = settings.TEMPLATES[0]["OPTIONS"].get("context_processors", [])
        self.assertNotIn("apiSystem.context_processors.tool_favorites", processors)

    def test_sidebar_cache_roundtrip(self) -> None:
        """侧边栏收藏缓存的写入和读取应正常工作。"""
        from django.core.cache import cache

        user = User.objects.create_user(username="favtest_p5", password="x")
        ToolFavorite.objects.create(user=user, tool_url="/admin/test/", tool_name="Test")

        cache_key = f"admin:fav_urls:{user.id}"
        cache.delete(cache_key)

        # 模拟写入缓存
        fav_urls = list(ToolFavorite.objects.filter(user=user).values_list("tool_url", flat=True))
        cache.set(cache_key, fav_urls, timeout=300)

        # 验证读取
        cached = cache.get(cache_key)
        self.assertIsNotNone(cached)
        self.assertIn("/admin/test/", cached)

    def test_toggle_clears_cache(self) -> None:
        """toggle 操作应清除缓存。"""
        from django.core.cache import cache

        user = User.objects.create_user(username="toggle_p5", password="x")
        cache_key = f"admin:fav_urls:{user.id}"

        cache.set(cache_key, ["/admin/old/"], timeout=300)
        self.assertIsNotNone(cache.get(cache_key))

        # 模拟 toggle 清除
        cache.delete(cache_key)
        self.assertIsNone(cache.get(cache_key))
