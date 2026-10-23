"""案件材料整理（财务单据 OCR 分类 / 对账单比对）app 配置。

历史名称：``apps.evidence_sorting``。因业务与「证据管理」（apps.evidence）无关，
2026-10 只改 Python 包名与显示语义，**不改变 app label**。

为何保留 ``label = "evidence_sorting"``：
- 本 app 的模型 ``managed=False``（不建表），但``django_migrations`` 里已有
  ``evidence_sorting.0001_initial`` 记账。改 label 会让旧行变孤儿（库有/代码无）
  同时新行未应用，触发 ``scan_migration_anomalies`` 报错。
- 保留 label 则零迁移、零风险，包名与业务语义已由目录名表达。

若要彻底改为新 label，需配套一条数据迁移改写 ``django_migrations`` 的 app 列，
那属于需要用户确认的 migrate 操作，不应顺手做。
"""

from django.apps import AppConfig


class FinanceDocSortingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.finance_doc_sorting"
    label = "evidence_sorting"
    verbose_name = "案件材料整理"
