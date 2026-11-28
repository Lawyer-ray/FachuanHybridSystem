"""UI 动作工具族（``ui_*``）—— 工具面里唯一「不是业务 API」的一族。

这一族的工具不碰任何后端接口：函数体只把动作推给前端 SSE 通道
（``apps/agent/services/ui_action``），由页面自己执行。所以这里没有 ``client``
调用、没有业务领域逻辑，也**没有**手写的工具名——名字、描述、参数 schema、
风险档全部来自单源清单，见 :mod:`.register`。
"""

from __future__ import annotations
