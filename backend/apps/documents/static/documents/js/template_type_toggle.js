/**
 * 文档模板类型切换功能
 * 支持两级选择：
 * 1. 第一级：合同文书模板 vs 案件文书模板
 * 2. 第二级：合同文书模板下细分为合同模板和补充协议模板
 * 3. 文件来源互斥选择
 */

(function() {
    'use strict';

    function toggleFieldsByTemplateType() {
        const contractRadio = document.querySelector('input[name="template_type"][value="contract"]');
        const caseRadio = document.querySelector('input[name="template_type"][value="case"]');

        const contractSubTypeFieldset = document.querySelector('.field-contract_sub_type');
        const caseSubTypeFieldset = document.querySelector('.field-case_sub_type');
        const contractTypesFieldset = document.querySelector('.field-contract_types_field');
        const caseTypesFieldset = document.querySelector('.field-case_types_field');
        const caseStageFieldset = document.querySelector('.field-case_stage_field');
        const legalStatusesFieldset = document.querySelector('.field-legal_statuses_field');
        const legalStatusMatchModeFieldset = document.querySelector('.field-legal_status_match_mode');

        if (!contractRadio || !caseRadio) {
            return;
        }

        function updateFieldsVisibility() {
            const isContract = contractRadio.checked;
            const isCase = caseRadio.checked;

            // 显示/隐藏字段
            if (contractSubTypeFieldset) {
                contractSubTypeFieldset.style.display = isContract ? 'block' : 'none';
            }

            if (caseSubTypeFieldset) {
                caseSubTypeFieldset.style.display = isCase ? 'block' : 'none';
            }

            if (contractTypesFieldset) {
                contractTypesFieldset.style.display = isContract ? 'block' : 'none';
            }

            if (caseTypesFieldset) {
                caseTypesFieldset.style.display = isCase ? 'block' : 'none';
            }

            if (caseStageFieldset) {
                caseStageFieldset.style.display = isCase ? 'block' : 'none';
            }

            if (legalStatusesFieldset) {
                legalStatusesFieldset.style.display = isCase ? 'block' : 'none';
            }

            if (legalStatusMatchModeFieldset) {
                legalStatusMatchModeFieldset.style.display = isCase ? 'block' : 'none';
            }

            // 清空不相关字段的选择
            if (isContract) {
                // 选择合同模板时，清空案件相关字段
                const caseSubTypeRadios = document.querySelectorAll('input[name="case_sub_type"]');
                caseSubTypeRadios.forEach(radio => {
                    radio.checked = false;
                });

                const caseTypeCheckboxes = document.querySelectorAll('input[name="case_types_field"]');
                caseTypeCheckboxes.forEach(checkbox => {
                    checkbox.checked = false;
                });

                const caseStageSelect = document.querySelector('select[name="case_stage_field"]');
                if (caseStageSelect) {
                    caseStageSelect.value = '';
                }

                const legalStatusCheckboxes = document.querySelectorAll('input[name="legal_statuses_field"]');
                legalStatusCheckboxes.forEach(checkbox => {
                    checkbox.checked = false;
                });
            } else if (isCase) {
                // 选择案件模板时，清空合同相关字段
                const contractTypeCheckboxes = document.querySelectorAll('input[name="contract_types_field"]');
                contractTypeCheckboxes.forEach(checkbox => {
                    checkbox.checked = false;
                });

                // 清空合同子类型选择
                const contractSubTypeRadios = document.querySelectorAll('input[name="contract_sub_type"]');
                contractSubTypeRadios.forEach(radio => {
                    radio.checked = false;
                });
            }
        }

        // 绑定事件监听器
        contractRadio.addEventListener('change', updateFieldsVisibility);
        caseRadio.addEventListener('change', updateFieldsVisibility);

        // 初始化显示状态
        updateFieldsVisibility();
    }

    function handleFileSourceConflict() {
        const existingFileSelect = document.querySelector('select[name="existing_file"]');
        const fileInput = document.querySelector('input[name="file"]');
        const filePathInput = document.querySelector('input[name="file_path"]');

        if (!existingFileSelect || !fileInput || !filePathInput) {
            return;
        }

        function clearOtherSources(currentSource) {
            if (currentSource !== 'existing_file') {
                existingFileSelect.value = '';
            }
            if (currentSource !== 'file') {
                fileInput.value = '';
            }
            if (currentSource !== 'file_path') {
                filePathInput.value = '';
            }
        }

        // 监听从模板库选择
        existingFileSelect.addEventListener('change', function() {
            if (this.value) {
                clearOtherSources('existing_file');
            }
        });

        // 监听文件上传
        fileInput.addEventListener('change', function() {
            if (this.files && this.files.length > 0) {
                clearOtherSources('file');
            }
        });

        // 监听文件路径输入
        filePathInput.addEventListener('input', function() {
            if (this.value.trim()) {
                clearOtherSources('file_path');
            }
        });

        // 页面加载时处理初始状态冲突
        // 如果existing_file有值且file_path也有值，清空file_path
        if (existingFileSelect.value && filePathInput.value) {
            filePathInput.value = '';
        }
    }

    // DOM加载完成后执行
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            toggleFieldsByTemplateType();
            handleFileSourceConflict();
        });
    } else {
        toggleFieldsByTemplateType();
        handleFileSourceConflict();
    }
})();
