"""规则提取子包：身份证/营业执照/叙述式规则与置信度（纯函数）。

证件类型分发由 ``IdentityExtractionService._extract_by_rules`` 负责，
以便保留实例级 patch 点。
"""
