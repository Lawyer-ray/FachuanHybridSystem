"""多答评审内核（B2）。

按职责分文件，避免"一个 judge 文件既拼 prompt 又算分"的老路：

- ``rubric.py``：评分项定义 + 结算公式（正分进分母、负分只在分子扣）；
- ``judge_prompt.py``：带 nonce 的字段边界、候选正文净化、三态解析；
- ``judge_client.py``：走 ``apps.core.llm.client`` 的判定调用与有限重试；
- ``jury.py``：多栏 × 多 rubric 的并发编排、全局并发闸门与打分后的成团接线；
- ``entail.py``：判等实现（两段结论是否实质等价，判不了返回 None）与判等并发口径；
- ``judge_models.py``：judge 模型的四步解析（请求 → 平台配置 → 本轮模型 → 422）；
- ``score.py``：把逐条判定汇总成 ``LaneReview`` / ``Review``（纯计算）；
- ``store.py``：轮次答案读取与评审快照落库（API 层不碰 ORM）。

本包只产出评审结果（``stage="shadow"``），不触发任何自动动作。
"""
