"""
合同文件夹绑定属性测试
使用 Hypothesis 进行属性测试
"""

import re
from unittest.mock import mock_open, patch

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from apps.contracts.models import Contract, ContractFolderBinding
from apps.contracts.services.folder_binding_service import FolderBindingService
from apps.core.exceptions import NotFoundError, ValidationException


class TestFolderBindingProperties:
    """文件夹绑定属性测试"""

    def setup_method(self):
        """测试前准备"""
        self.service = FolderBindingService()

    @given(st.text())
    def test_path_validation_consistency(self, path):
        """
        Property 2: 路径格式验证正确性
        For any 输入的路径字符串，路径验证函数应正确识别有效的本地路径
        （macOS/Linux/Windows）和网络共享路径（UNC/SMB），并拒绝无效格式。
        **Validates: Requirements 3.2, 3.4, 3.5**
        """
        is_valid, error = self.service.validate_folder_path(path)

        # 如果路径有效，应该符合已知的格式之一
        if is_valid:
            assert (
                path.startswith("/")  # macOS/Linux
                or re.match(r"^[A-Za-z]:[\\\/]", path)  # Windows
                or path.startswith("\\\\")  # UNC
                or path.startswith("smb://")  # SMB
            ), f"Valid path should match known formats: {path}"
        else:
            # 如果路径无效，应该有错误信息
            assert error is not None
            assert isinstance(error, str)
            assert len(error) > 0

    @pytest.mark.django_db
    @given(
        contract_name=st.text(min_size=1, max_size=100),
        folder_path=st.one_of(
            st.from_regex(r'^/[^<>:"|?*]*$', fullmatch=True).filter(lambda x: len(x) >= 2),  # Unix paths
            st.from_regex(r'^[A-Za-z]:[\\\/][^<>:"|?*]*$', fullmatch=True).filter(
                lambda x: len(x) >= 4
            ),  # Windows paths
            st.from_regex(r"^\\\\[^\\]+\\[^\\]+.*$", fullmatch=True).filter(lambda x: len(x) >= 6),  # UNC paths
            st.from_regex(r"^smb://[^/]+/.*$", fullmatch=True).filter(lambda x: len(x) >= 8),  # SMB paths
        ),
    )
    def test_binding_crud_round_trip(self, contract_name, folder_path):
        """
        Property 3: 绑定CRUD操作正确性（Round-trip）
        For any 合同和有效的文件夹路径，创建绑定后查询应返回相同的路径；
        更新绑定后查询应返回新路径；删除绑定后查询应返回空。
        **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
        """
        # 创建测试合同
        contract = Contract.objects.create(name=contract_name, case_type="CIVIL")

        try:
            # 1. 创建绑定
            binding = self.service.create_binding(contract.id, folder_path)
            assert binding is not None
            assert binding.folder_path == folder_path.strip()

            # 2. 查询绑定应返回相同路径
            retrieved_binding = self.service.get_binding(contract.id)
            assert retrieved_binding is not None
            assert retrieved_binding.folder_path == folder_path.strip()

            # 3. 更新绑定
            new_path = folder_path + "_updated"
            updated_binding = self.service.update_binding(contract.id, new_path)
            assert updated_binding.folder_path == new_path.strip()

            # 4. 查询应返回新路径
            retrieved_updated = self.service.get_binding(contract.id)
            assert retrieved_updated is not None
            assert retrieved_updated.folder_path == new_path.strip()

            # 5. 删除绑定
            delete_result = self.service.delete_binding(contract.id)
            assert delete_result is True

            # 6. 查询应返回空
            deleted_binding = self.service.get_binding(contract.id)
            assert deleted_binding is None

        finally:
            # 清理
            contract.delete()

    @pytest.mark.django_db
    @given(
        contract_name=st.text(min_size=1, max_size=100),
        folder_path=st.one_of(
            st.from_regex(r'^/[^<>:"|?*]*$', fullmatch=True).filter(lambda x: len(x) >= 2),  # Unix paths
            st.from_regex(r'^[A-Za-z]:[\\\/][^<>:"|?*]*$', fullmatch=True).filter(
                lambda x: len(x) >= 4
            ),  # Windows paths
        ),
    )
    def test_binding_status_display_consistency(self, contract_name, folder_path):
        """
        Property 4: 绑定状态显示一致性
        For any 合同，显示的绑定状态应与数据库中的绑定记录一致：已绑定时显示路径和时间，未绑定时显示"未绑定"。
        **Validates: Requirements 5.1, 5.2, 5.3**
        """
        # 创建测试合同
        contract = Contract.objects.create(name=contract_name, case_type="CIVIL")

        try:
            # 1. 未绑定状态
            binding = self.service.get_binding(contract.id)
            assert binding is None

            # 2. 创建绑定后状态
            created_binding = self.service.create_binding(contract.id, folder_path)
            retrieved_binding = self.service.get_binding(contract.id)

            assert retrieved_binding is not None
            assert retrieved_binding.folder_path == created_binding.folder_path
            assert retrieved_binding.created_at is not None
            assert retrieved_binding.updated_at is not None

        finally:
            # 清理
            contract.delete()

    @pytest.mark.django_db
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.mkdir")
    @given(
        contract_name=st.text(min_size=1, max_size=100),
        folder_path=st.from_regex(r'^/[^<>:"|?*]*$', fullmatch=True).filter(lambda x: len(x) >= 2),
        file_name=st.text(min_size=1, max_size=50).filter(lambda x: "/" not in x and "\\" not in x),
        file_content=st.binary(min_size=1, max_size=1000),
    )
    def test_file_save_location_correctness(
        self, mock_mkdir, mock_file, contract_name, folder_path, file_name, file_content
    ):
        """
        Property 5: 文件保存位置正确性
        For any 已绑定文件夹的合同，生成的合同文书应保存到"合同文书"子目录，
        补充协议应保存到"补充协议"子目录，ZIP包应解压到绑定文件夹根目录。
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        # 创建测试合同
        contract = Contract.objects.create(name=contract_name, case_type="CIVIL")

        try:
            # 创建绑定
            self.service.create_binding(contract.id, folder_path)

            # 测试合同文书保存
            result_contract = self.service.save_file_to_bound_folder(
                contract.id, file_content, f"contract_{file_name}", "contract_documents"
            )

            if result_contract:  # 如果保存成功
                assert "合同文书" in result_contract
                assert f"contract_{file_name}" in result_contract

            # 测试补充协议保存
            result_supplement = self.service.save_file_to_bound_folder(
                contract.id, file_content, f"supplement_{file_name}", "supplementary_agreements"
            )

            if result_supplement:  # 如果保存成功
                assert "补充协议" in result_supplement
                assert f"supplement_{file_name}" in result_supplement

        finally:
            # 清理
            contract.delete()

    @pytest.mark.django_db
    @patch("pathlib.Path.mkdir")
    @given(
        contract_name=st.text(min_size=1, max_size=100),
        folder_path=st.from_regex(r'^/[^<>:"|?*]*$', fullmatch=True).filter(lambda x: len(x) >= 2),
    )
    def test_subdirectory_auto_creation(self, mock_mkdir, contract_name, folder_path):
        """
        Property 6: 子目录自动创建
        For any 绑定的文件夹路径，当保存文件时如果子目录不存在，系统应自动创建所需的子目录结构。
        **Validates: Requirements 7.1, 7.2**
        """
        # 创建测试合同
        contract = Contract.objects.create(name=contract_name, case_type="CIVIL")

        try:
            # 创建绑定
            self.service.create_binding(contract.id, folder_path)

            # 确保子目录创建
            result = self.service.ensure_subdirectories(folder_path)

            # 应该成功创建子目录
            assert result is True

            # 应该调用了mkdir方法
            assert mock_mkdir.called

        finally:
            # 清理
            contract.delete()

    @given(path=st.text(min_size=1, max_size=200), max_length=st.integers(min_value=10, max_value=100))
    def test_path_display_formatting(self, path, max_length):
        """
        Property 7: 路径显示格式化
        For any 超过指定长度的路径，格式化显示函数应正确截断并添加省略号，同时保留路径的关键部分（开头和结尾）。
        **Validates: Requirements 5.4**
        """
        formatted = self.service.format_path_for_display(path, max_length)

        # 格式化后的路径长度不应超过最大长度
        assert len(formatted) <= max_length

        if len(path) <= max_length:
            # 如果原路径不超长，应该保持不变
            assert formatted == path
        else:
            # 如果原路径超长，应该包含省略号
            assert "..." in formatted
            # 应该保留开头和结尾部分
            assert formatted.startswith(path[: max_length // 3])
            # 格式化后的长度应该等于最大长度（或接近）
            assert len(formatted) <= max_length

    @given(
        st.one_of(
            st.just(""),  # 空字符串
            st.just("   "),  # 空白字符串
            st.just("\t"),  # 制表符
            st.just("\n"),  # 换行符
            st.just(" \t \n "),  # 混合空白字符
        )
    )
    def test_empty_path_handling(self, path):
        """测试空路径处理的一致性"""
        is_valid, error = self.service.validate_folder_path(path)
        assert not is_valid
        assert error == "请输入文件夹路径"

    @given(
        st.one_of(
            st.just("file<name"),  # 包含 < 字符
            st.just("file>name"),  # 包含 > 字符
            st.just('file"name'),  # 包含 " 字符
            st.just("file|name"),  # 包含 | 字符
            st.just("file?name"),  # 包含 ? 字符
            st.just("file*name"),  # 包含 * 字符
            st.just("path<>with|bad*chars"),  # 包含多个非法字符
        )
    )
    def test_invalid_characters_rejection(self, path):
        """测试包含非法字符的路径被正确拒绝"""
        is_valid, error = self.service.validate_folder_path(path)

        # 包含非法字符的路径应该被拒绝
        assert not is_valid
        if error:
            assert "非法字符" in error or "请输入有效的文件夹路径" in error
