"""`CaseOut` / `CaseSlimOut` 必须下发 `previous_case_id`（前端的程序线关系）。

为什么值得一个用例：合同详情页顶部的程序链要按「二审接的是哪条一审、执行接的是哪条二审」
分出几条程序线（`frontend/.../detail/chain-domain.ts` 的 `caseBranches`）。这个字段漏了
**不会报错**——前端拿不到关系就退化成「多个案件 = 多条互不相干的线」，页面照样渲染，
只是把「一审 → 二审」画成两个孤立的点、把归属讲错（271 号形态：两个二审、只有一个进了
执行）。静默退化只能靠契约用例拦。

纯声明层测试：不建库、不碰 ORM。
"""

from apps.cases.schemas.case_schemas import CASE_SCALAR_FIELDS, CaseOut
from apps.cases.schemas.case_slim_schemas import CaseSlimOut


class TestPreviousCaseIdIsExposed:
    def test_full_schema_has_it(self):
        assert "previous_case_id" in CaseOut.model_fields

    def test_slim_schema_has_it_too(self):
        # 标量列在完整版与瘦身版之间必须同口径，否则「完整版有、瘦身版没有」的
        # 缺口会像 is_filed 当年那样一个个冒出来
        assert "previous_case_id" in CaseSlimOut.model_fields

    def test_stays_out_of_the_shared_scalar_list(self):
        # CASE_SCALAR_FIELDS 是模型标量列的公共名单（两张 schema 共用）。
        # 它收的是 Case 自己的列；FK 只给裸 id（与 contract_id 同一处理），
        # 所以这里不该出现 previous_case_id。
        assert "previous_case_id" not in CASE_SCALAR_FIELDS

    def test_resolver_reads_orm_and_dict(self):
        class _Case:
            previous_case_id = 42

        assert CaseOut.resolve_previous_case_id(_Case()) == 42
        assert CaseOut.resolve_previous_case_id({"previous_case_id": 42}) == 42
        # 根案件（没有前序）→ None，不是 0 / ""：前端按 null 判「这条线从它开始」
        assert CaseOut.resolve_previous_case_id({"previous_case_id": None}) is None
