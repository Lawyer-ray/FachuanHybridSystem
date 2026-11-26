"""pdf_splitting ``summary`` 载荷的键登记表：每个键要么有界面落点，要么明确声明只给排障看。

为什么需要这份登记
------------------
v25.x → v27.26 连续两次出现「后端算了、写了 ``summary``、前端一个键都没读」：

- ``engine_disagreements_judge``：v27.25.4 就算出来并落进 ``summary``，直到 v27.26.0 才接上界面；
- ``degenerate_pages``：取字阶段一直在算，直到 v27.26.1 才接上界面。

两次都是靠人盯 changelog 发现的。``summary`` 是后端与前端之间**没有 schema 的**自由字典
（``PdfSplitJob.summary_payload`` 不进 openapi 生成物），少接一个键不报错、不抛异常，
只表现为「页面上什么都没有」——这类静默丢失只能靠登记 + 结构测试守。

新加一个 ``summary`` 键要做什么
------------------------------
1. **先选边**：律师能不能在界面上感知它？
   律师要据此决定核不核对、改不改名的 → 登记进 ``UI_SUMMARY_KEYS``；
   只有计数、批量数、降级原因、平台/模板版本这类排障信息 → 登记进 ``DIAG_SUMMARY_KEYS``。
2. **登记成 UI 就必须补界面落点**：``frontend/src`` 里要真的出现该键名。
   没有落点就是「算了但没人看」，``backend/tests/ci/structure/test_pdf_split_summary_keys.py``
   会红——这正是它的用途，不要为了让测试变绿把它改登记成 DIAG。
3. **登记成 DIAG 要写清为什么律师不用看**（一句话，少于 8 个字符算没写）。
   写不出来的，多半其实属于 UI。
4. **间接进入 ``summary`` 的键**（经 ``**splat`` 或辅助函数展开）由该测试的 ``KNOWN_DYNAMIC``
   兜住；新键若走这种路径，两处都要加，否则测试会把它当成「未登记的新键」。
5. 想删键：先确认 ``frontend/src`` 不再读它，再从登记表与 ``summary`` 里一起删。

本模块**不被业务代码 import**：它只是声明 + 给测试消费。特意不 import 任何东西，
让结构测试能在不起 Django 应用的前提下读它（被测代码的扫描由 ``ast`` 完成）。
"""

from __future__ import annotations

#: 律师能在界面上感知的键：「这个键没接上」= 界面少了一条他该看到的证据。
#: 值是**为什么律师必须看得到**，不是键的含义（含义在读写处，这里只答「不接上的代价」）。
UI_SUMMARY_KEYS: dict[str, str] = {
    # 页级画像
    "page_quality": "图纸页/稀疏页/证件缺件清单——阅读器靠它标段行、提示「本段含图纸」与缺哪份证件",
    "degenerate_pages": "云端读成复读循环/空返回、已被本地 OCR 兜底的页——这些页正文可疑，律师必须逐段看到提示",
    "table_geometry": "表格几何观测（含列数突变）——数字表头的列可能被并/拆，必须提示到具体页",
    # 跨页一致性
    "inconsistencies": "同一枚章或同一字段被识成两种写法——界面出全卷清单并给「更推荐改成什么」",
    # 双引擎
    "engine_disagreements": "两引擎正文分歧逐页记录——正文内联对照，律师可采用某一侧或进编辑态",
    "engine_disagreements_judge": "分歧自动裁定总账（enabled/requested/reason/条数）——界面据此说清「开了没生效」还是「一条都没裁成」",
    # 分段
    "segment_backend": "本次分段实际后端（llm / rule）——规则降级时段行要标「需重点复核」",
}

#: 只在后台/日志/排障里有用的键：不接界面的代价只是「以后查账要多翻一层」，不是「律师少看到证据」。
DIAG_SUMMARY_KEYS: dict[str, str] = {
    # ── 任务级选择的快照（界面回显读的是 PdfSplitJob 的同名列，不是这里的副本）──
    "split_mode": "拆分模式快照；界面读 PdfSplitJob.split_mode 渲染，这份副本只供排障对账",
    "template_key": "模板标识快照；界面按 job.template_key 查模板表取名，不读这份",
    "template_label": "模板中文名快照；界面按 job.template_key 查模板表取名，不读这份副本",
    "template_version": "模板版本号只用于回答「这份是按哪版模板切的」，界面不展示",
    "ocr_profile": "取字档位快照；界面回显读 job.ocr_profile，这份只供排障对账",
    "layout_mode": "版面策略快照；界面读 job.layout_mode 与表单状态，这份只供排障对账",
    "cloud_backend": "首选云端平台快照；界面读 job.cloud_backend，这份只供排障对账",
    "dual_engines": "选中的比对引擎快照；界面读 job.dual_engines，这份只供排障对账",
    "ocr_judge_enabled": "是否要求分歧自动裁定；界面读 job.ocr_judge_enabled，这份只供排障对账",
    "segment_strategy": "分段策略快照；界面读 job.segment_strategy，这份只供排障对账",
    # ── 分段计数 ──
    "segment_count": "分段总数；界面直接用返回的 segments 数组长度，不读这个汇总计数",
    "recognized_count": "已识别段数；界面按 segments 逐条统计，不用这个汇总计数",
    "unrecognized_count": "未识别段数；界面按 segments 逐条统计，不用这个汇总计数",
    "page_split": "按页机械切分路径的标记位；界面的模式判定读 split_mode，不读这个布尔",
    # ── 分段后端细节 ──
    "segment_llm_fallback_reason": "LLM 分段失败降级到规则引擎的原因串；界面只读 segment_backend 定标，原因留给排障",
    "segment_total_batches": "分批分段一共几批；纯排障计数，界面不展示",
    "segment_rule_batches": "其中被规则引擎切掉的批次数；纯排障计数，界面不展示",
    "segment_wholebook_budget": "整本一次分段时 LLM 的轮次/耗时记账；纯排障数字，界面不展示",
    "segment_batch_backend": "交叉策略里分批那一侧用的后端；排障对账用，界面只读 segment_backend",
    "segment_boundary_disagreement_pages": "整本与分批切点不一致的页号表；段上的 review_flag 已把影响带到界面，这张表只供排障定位",
    "segment_boundary_disagreement_total": "切点不一致的页数合计；纯排障计数，界面靠段上的 review_flag 提示",
    # `segment_strategy` 同时经上面这条路径进入 summary，但它静态可见（下面任务级快照一组），
    # 所以只登记一次，不重复列。
    # ── 取字参数与云端链路 ──
    "ocr_dpi": "取字渲染的 DPI；纯排障参数，界面不展示",
    "ocr_model": "云端 OCR 模型版本；只在排障时对账识别效果",
    "ocr_workers": "取字并发数；纯排障参数，界面不展示",
    "ocr_provider": "本轮产物真正出自哪个平台；排障对账坐标口径用，界面读的是 job.cloud_backend",
    "material_kind": "整本更像电子件/扫描件/混合的标签；界面按逐页结果判定，不用这个汇总",
    "cloud_used": "本次是否真的调过云端；排障判据，界面不展示",
    "cloud_failover_from": "容灾时从哪些平台退下来的；纯排障链，界面不展示",
    "cloud_candidates": "本次参与容灾的候选平台；纯排障链，界面不展示",
    "ocr_fallback_reason": "云端取字失败/降级的原因串；排障定位用，界面不展示",
    "layout_unavailable_reason": "开了版面却没生效的具体原因；排障定位用，界面不展示",
    "ocr_cloud_cache_profile": "云端结果缓存的档位键；纯排障标识",
    "ocr_cloud_cache_hit_count": "云端结果缓存命中数；纯排障计数",
    "ocr_cache_hit_count": "页缓存命中数；只用来说明「这次为什么快」",
    "ocr_miss_count": "本轮真正需要取字的页数；纯排障计数",
    # ── 预算与补救记账 ──
    "stage_budget_seconds": "本阶段墙钟预算秒数；只在排障「为什么被砍」时看",
    "stage_budget_remaining_seconds": "阶段结束时剩余预算秒数；纯排障数字",
    "ocr_budget_skipped_count": "因预算不足没发云端调用的页数；纯排障计数",
    "ocr_budget_skipped_pages": "因预算不足没发云端调用的页号表；纯排障明细",
    "image_rescue_pages": "图片块补救救回了哪几页；排障记账，界面不展示",
    "image_rescue_chars": "图片块补救救回多少字；纯排障计数",
    "image_rescue_reused": "复用已有 VL 结果的页数；纯排障计数",
    "image_rescue_skipped_budget": "因预算不足放弃补救的页数；纯排障计数",
    "dedupe_skipped_pages": "重复页去重省掉的页数；纯排障计数",
    "dedupe_filled_pages": "重复页去重补回的页数；纯排障计数",
    # ── 双引擎/一致性里只供对账的伴生块 ──
    "inconsistency_total": "不一致条目真实总数；界面只渲染 inconsistencies 列表，这个计数不进界面",
    "engine_disagree_summary": "分歧按严重度（high/medium/low）的计数；界面按 engine_disagreements 逐条渲染",
    "dual_engine": "双引擎运行参数与不可用原因；排障对账用，界面读 job.dual_engines",
    "rotated_backfill": "转正页回填的逐页记账与跳过原因；只在查「这页为什么没被换掉」时看",
}

#: 所有登记过的键。``summary`` 里出现但不在这个集合里的键 = 有人加了键没登记。
ALL_SUMMARY_KEYS: frozenset[str] = frozenset(UI_SUMMARY_KEYS) | frozenset(DIAG_SUMMARY_KEYS)
