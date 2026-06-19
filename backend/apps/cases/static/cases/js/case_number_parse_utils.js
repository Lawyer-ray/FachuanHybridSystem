/**
 * 案件案号解析 — 工具函数与 DOM 辅助
 *
 * 提供：
 * 1. showToast / getCSRFToken 通用工具
 * 2. getCaseNumberInlineGroup / getCaseNumberRows DOM 辅助
 * 3. isExecutionStageSelected / toggleExecutionParameterSections 执行阶段联动
 *
 * 必须在 case_number_parse_upload.js 和 case_number_parse.js 之前加载。
 */
;(function() {
    'use strict';

    // ============================================================
    // 工具函数
    // ============================================================

    /**
     * 显示 Toast 通知
     * @param {string} message - 消息内容
     * @param {string} [type='success'] - 消息类型: success / error
     */
    function showToast(message, type) {
        type = type || 'success';
        var container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        var toast = document.createElement('div');
        toast.className = 'toast ' + type;
        toast.textContent = message;
        container.appendChild(toast);
        toast.offsetHeight; // 触发重绘
        toast.classList.add('show');
        setTimeout(function() {
            toast.classList.remove('show');
            setTimeout(function() {
                container.removeChild(toast);
            }, 300);
        }, 3000);
    }

    /**
     * 从 cookie 获取 CSRF Token
     * @returns {string|null}
     */
    function getCSRFToken() {
        var name = 'csrftoken';
        var cookieValue = null;
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
        return cookieValue;
    }

    // ============================================================
    // DOM 查询辅助
    // ============================================================

    /**
     * 获取案号内联表单组
     * @returns {Element|null}
     */
    function getCaseNumberInlineGroup() {
        return (
            document.querySelector('#case_numbers-group') ||
            document.querySelector(".inline-group[id$='case_numbers-group']")
        );
    }

    /**
     * 获取所有案号行（兼容 tabular 和 stacked）
     * @param {Element} inline - 内联表单组
     * @returns {Element[]}
     */
    function getCaseNumberRows(inline) {
        if (!inline) return [];
        var result = [];
        var tabularRows = inline.querySelectorAll('tbody tr');
        if (tabularRows.length > 0) {
            for (var i = 0; i < tabularRows.length; i++) {
                var tr = tabularRows[i];
                if (tr.classList.contains('empty-form')) continue;
                result.push(tr);
            }
            return result;
        }

        var stackedRows = inline.querySelectorAll('.inline-related');
        for (var j = 0; j < stackedRows.length; j++) {
            var block = stackedRows[j];
            if (block.classList.contains('empty-form') || block.classList.contains('djn-empty-form')) continue;
            if (!block.querySelector('.field-number') && !block.querySelector('.field-document_file')) continue;
            result.push(block);
        }
        return result;
    }

    // ============================================================
    // 执行阶段联动
    // ============================================================

    /**
     * 判断当前阶段是否为"执行"
     * @returns {boolean}
     */
    function isExecutionStageSelected() {
        var stageSelect = document.getElementById('id_current_stage');
        if (!stageSelect) return false;
        return (stageSelect.value || '').trim() === 'enforcement';
    }

    /**
     * 根据当前阶段显示/隐藏执行参数区域
     */
    function toggleExecutionParameterSections() {
        var inline = getCaseNumberInlineGroup();
        if (!inline) return;

        var show = isExecutionStageSelected();
        var fieldsets = inline.querySelectorAll('.case-number-execution-fieldset');
        for (var i = 0; i < fieldsets.length; i++) {
            fieldsets[i].classList.toggle('is-hidden-by-stage', !show);
        }
    }

    /**
     * 绑定 current_stage 下拉框的 change 事件
     */
    function bindCurrentStageWatcher() {
        var stageSelect = document.getElementById('id_current_stage');
        if (!stageSelect || stageSelect.dataset.executionWatcherBound === 'true') {
            return;
        }
        stageSelect.dataset.executionWatcherBound = 'true';
        stageSelect.addEventListener('change', function() {
            toggleExecutionParameterSections();
        });
    }

    // ============================================================
    // 暴露到共享命名空间
    // ============================================================

    window.CaseNumberParse = {
        showToast: showToast,
        getCSRFToken: getCSRFToken,
        getCaseNumberInlineGroup: getCaseNumberInlineGroup,
        getCaseNumberRows: getCaseNumberRows,
        isExecutionStageSelected: isExecutionStageSelected,
        toggleExecutionParameterSections: toggleExecutionParameterSections,
        bindCurrentStageWatcher: bindCurrentStageWatcher
    };

})();
