"""云存储 app（自 apps/core/cloud_storage 拆分而来）。

import 路径统一为 apps.cloud_storage.*；数据库表名钉死为 core_cloudstorageaccount，零数据搬迁。
注意：__init__.py 保持轻量，不得在此导入 models（会破坏 Django app 注册顺序）。
"""
