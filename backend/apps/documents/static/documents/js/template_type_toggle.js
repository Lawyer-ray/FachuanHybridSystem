/**
 * 文档模板类型切换功能
 * 支持两级选择：
 * 1. 第一级：合同文书模板 vs 案件文书模板
 * 2. 第二级：合同文书模板下细分为合同模板和补充协议模板
 * 3. 文件来源互斥选择
 */

(function() {
    'use strict';

    function updateFieldsVisibility() {
        const contractRadio = document.querySelector('input[name="template_type"][value="contract"]');
        const caseRadio = document.querySelector('input[name="template_type"][value="case"]');

        if (!contractRadio || !caseRadio) {
            return;
        }

        const isContract = contractRadio.checked;
        const isCase = caseRadio.checked;

        // 字段选择器与对应显示条件的映射
        const fieldMap = {
            '.field-contract_sub_type': isContract,
            '.field-contract_types_field': isContract,
            '.field-case_sub_type': isCase,
            '.field-case_types_field': isCase,
            '.field-case_stage_field': isCase,
            '.field-legal_statuses_field': isCase,
            '.field-legal_status_match_mode': isCase,
            '.field-applicable_institutions_field': isCase
        };

        Object.entries(fieldMap).forEach(function(entry) {
            var el = document.querySelector(entry[0]);
            if (el) {
                el.style.display = entry[1] ? 'block' : 'none';
            }
        });

        // 清空不相关字段的选择
        if (isContract) {
            document.querySelectorAll('input[name="case_sub_type"]').forEach(function(r) { r.checked = false; });
            document.querySelectorAll('input[name="case_types_field"]').forEach(function(c) { c.checked = false; });
            var caseStageSelect = document.querySelector('select[name="case_stage_field"]');
            if (caseStageSelect) { caseStageSelect.value = ''; }
            document.querySelectorAll('input[name="legal_statuses_field"]').forEach(function(c) { c.checked = false; });
        } else if (isCase) {
            document.querySelectorAll('input[name="contract_types_field"]').forEach(function(c) { c.checked = false; });
            document.querySelectorAll('input[name="contract_sub_type"]').forEach(function(r) { r.checked = false; });
        }
    }

    function toggleFieldsByTemplateType() {
        // 使用事件委托，避免 DOM 重建导致事件丢失
        document.addEventListener('change', function(e) {
            if (e.target && e.target.name === 'template_type') {
                updateFieldsVisibility();
            }
        });

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
    function init() {
        toggleFieldsByTemplateType();
        handleFileSourceConflict();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // 兜底：确保在所有资源加载后也执行一次
    window.addEventListener('load', function() {
        updateFieldsVisibility();
    });
})();
