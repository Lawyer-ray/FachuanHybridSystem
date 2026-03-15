"""
合同审查相关 Protocol 接口定义

包含: IReviewService
"""

from pathlib import Path
from typing import Any, Protocol
from uuid import UUID


class IReviewService(Protocol):
    """
    合同审查服务接口

    定义合同审查服务的公共方法，供其他模块使用
    """

    def upload_contract(
        self,
        file: Any,
        user: Any,
        model_name: str = "",
    ) -> Any:
        """
        上传合同：验证 → 保存 → 提取内容 → 识别甲乙方 → 创建任务

        Args:
            file: 上传的 docx 文件
            user: 操作用户
            model_name: LLM 模型名称

        Returns:
            ReviewTask 任务对象
        """
        ...

    def confirm_party(
        self,
        task_id: UUID,
        represented_party: str,
        user: Any,
        reviewer_name: str = "",
        selected_steps: list[str] | None = None,
    ) -> Any:
        """
        确认代表方，提交异步审查任务

        Args:
            task_id: 任务 ID
            represented_party: 用户代表的各方 (party_a/party_b/party_c/party_d)
            user: 操作用户
            reviewer_name: 修订人名称
            selected_steps: 选中的处理步骤

        Returns:
            ReviewTask 任务对象
        """
        ...

    def get_task_status(self, task_id: UUID) -> Any:
        """
        查询任务状态

        Args:
            task_id: 任务 ID

        Returns:
            ReviewTask 任务对象
        """
        ...

    def get_result_file(self, task_id: UUID) -> Path:
        """
        获取结果文件路径

        Args:
            task_id: 任务 ID

        Returns:
            输出文件路径
        """
        ...

    def get_original_file(self, task_id: UUID) -> Path:
        """
        获取原始上传文件路径

        Args:
            task_id: 任务 ID

        Returns:
            原始文件路径
        """
        ...
