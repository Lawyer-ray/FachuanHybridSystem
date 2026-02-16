/**
 * 案件表单 JavaScript
 * 处理案件类型变化时的案由自动填充
 */

(function() {
    'use strict';

    // 等待 DOM 和 Alpine.js 都准备好
    function init() {
        const caseTypeSelect = document.querySelector('#id_case_type');
        if (!caseTypeSelect) return;

        console.log('案件表单初始化，当前案件类型:', caseTypeSelect.value);

        // 页面加载时检查
        handleCaseTypeChange(caseTypeSelect.value);

        // 监听案件类型变化
        caseTypeSelect.addEventListener('change', function(e) {
            console.log('案件类型变化:', e.target.value);
            handleCaseTypeChange(e.target.value);
        });
    }

    function handleCaseTypeChange(caseType) {
        // 延迟执行，确保 Alpine.js 已经初始化
        setTimeout(function() {
            const causeInput = document.querySelector('#id_cause_of_action');
            if (!causeInput) {
                console.log('未找到案由输入框');
                return;
            }

            const currentValue = causeInput.value.trim();
            console.log('处理案件类型变化:', caseType, '当前案由:', currentValue);

            if (caseType === 'civil') {
                // 民事案件，如果案由为空则填写"合同纠纷"
                if (!currentValue) {
                    setCauseValue(causeInput, '合同纠纷');
                    console.log('已设置案由为: 合同纠纷');
                }
            } else {
                // 非民事案件，如果案由是"合同纠纷"则清空
                if (currentValue === '合同纠纷') {
                    setCauseValue(causeInput, '');
                    console.log('已清空案由');
                }
            }
        }, 100);
    }

    function setCauseValue(input, value) {
        // 直接设置输入框的值
        input.value = value;

        // 同步 Alpine.js 的状态
        const container = input.closest('.autocomplete-container');
        if (container && container._x_dataStack && container._x_dataStack[0]) {
            container._x_dataStack[0].query = value;
        }

        // 触发 input 事件让表单知道值已变化
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
