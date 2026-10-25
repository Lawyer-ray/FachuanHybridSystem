"""ReviewRevision 落库与「按当事人查合同」无关的审查修订单测。

重点覆盖：
- `_persist_revisions` 把 ReviewResult 转成结构化行（等级从【高/中/低】解析、标题截取）；
- 重跑审查时清理旧的待决策行，避免清单翻倍；
- 已决策（采纳/驳回）的行不被重跑清掉——律师的判断不能被 AI 重跑抹掉。
"""

from __future__ import annotations

import pytest

from apps.contract_review.models.review_revision import ReviewRevision, RevisionSeverity, RevisionStatus
from apps.contract_review.models.review_task import ReviewTask
from apps.contract_review.services.review.contract_reviewer import ReviewResult


class TestPersistRevisions:
    """_persist_revisions：AI 产出 → 结构化清单"""

    @pytest.mark.django_db
    def test_persists_rows_with_severity_and_title(self) -> None:
        from apps.contract_review.services.review.review_service import _persist_revisions

        task = ReviewTask.objects.create(original_file="a.docx")
        reviews = [
            ReviewResult(
                original="甲方于每季度首月十日内支付。",
                suggested="甲方于收到发票后三十日内支付。",
                reason="【高】付款节点过早，钱先付完工期失控。依据：民法典第509条。",
                paragraph_index=4,
            ),
            ReviewResult(
                original="提交仲裁解决。",
                suggested="提交佛山仲裁委员会仲裁。",
                reason="【低】仲裁机构未指明：可能致条款无效。",
                paragraph_index=12,
            ),
        ]

        n = _persist_revisions(task, reviews)

        assert n == 2
        rows = list(ReviewRevision.objects.filter(task=task).order_by("ordinal"))
        assert [r.ordinal for r in rows] == [0, 1]
        assert rows[0].severity == RevisionSeverity.HIGH
        assert rows[0].title == "付款节点过早，钱先付完工期失控"
        assert rows[0].paragraph_index == 4
        assert rows[1].severity == RevisionSeverity.LOW
        assert rows[1].title == "仲裁机构未指明"
        assert all(r.status == RevisionStatus.PENDING for r in rows)

    @pytest.mark.django_db
    def test_rerun_clears_pending_but_keeps_decided(self) -> None:
        from apps.contract_review.services.review.review_service import _persist_revisions

        task = ReviewTask.objects.create(original_file="a.docx")
        _persist_revisions(
            task,
            [
                ReviewResult("原文A", "改A", "【高】问题A。", 1),
                ReviewResult("原文B", "改B", "【中】问题B。", 2),
            ],
        )
        # 律师采纳了第 1 条
        first = ReviewRevision.objects.filter(task=task, ordinal=0).first()
        assert first is not None
        first.status = RevisionStatus.ACCEPTED
        first.save(update_fields=["status"])

        # 重跑审查
        _persist_revisions(
            task,
            [
                ReviewResult("原文A", "改A", "【高】问题A。", 1),
                ReviewResult("原文B", "改B", "【中】问题B。", 2),
                ReviewResult("原文C", "改C", "【低】问题C。", 3),
            ],
        )

        # 待决策的旧行被清掉重写，已采纳的保留
        kept = ReviewRevision.objects.filter(task=task, status=RevisionStatus.ACCEPTED)
        assert kept.count() == 1
        assert kept.first().original == "原文A"  # type: ignore[union-attr]
        pending = ReviewRevision.objects.filter(task=task, status=RevisionStatus.PENDING)
        assert pending.count() == 3

    @pytest.mark.django_db
    def test_empty_reviews_is_noop(self) -> None:
        from apps.contract_review.services.review.review_service import _persist_revisions

        task = ReviewTask.objects.create(original_file="a.docx")
        assert _persist_revisions(task, []) == 0
        assert ReviewRevision.objects.filter(task=task).count() == 0
