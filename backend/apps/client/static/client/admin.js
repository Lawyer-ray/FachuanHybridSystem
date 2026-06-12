/**
 * 客户 Admin 页面 JavaScript
 * 文本解析功能已迁移至 change_form.html 中的 textParserApp() (Alpine.js)
 */

(function($) {
    'use strict';

    // 使用 addEventListener 确保 DOM 加载完成后执行
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        // DOM 已经加载完成
        init();
    }

    function init() {
        initFormEnhancements();
        initIdCardValidation();
    }

    /**
     * 初始化表单增强功能
     */
    function initFormEnhancements() {
        // 客户类型变化时更新标签
        $('#id_client_type').on('change', function() {
            var clientType = $(this).val();
            var $idNumberLabel = $('label[for="id_id_number"]');

            if (clientType === 'natural') {
                $idNumberLabel.text('身份证号码:');
            } else {
                $idNumberLabel.text('统一社会信用代码:');
            }
        });

        // 触发初始化
        $('#id_client_type').trigger('change');
    }

    /**
     * 初始化身份证校验功能
     */
    function initIdCardValidation() {
        // 在身份证号输入框后添加校验按钮容器
        var $idNumberField = $('#id_id_number');
        if ($idNumberField.length === 0) return;

        // 创建校验按钮容器（初始隐藏）
        var $validateBtn = $('<button type="button" id="id-card-validate-btn" style="display:none; margin-left: 8px; padding: 6px 12px; background: #417690; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; vertical-align: middle;">校验</button>');
        var $validateResult = $('<span id="id-card-validate-result" style="margin-left: 8px; font-size: 13px;"></span>');

        $idNumberField.after($validateResult).after($validateBtn);

        // 监听客户类型变化
        $('#id_client_type').on('change', function() {
            var clientType = $(this).val();
            if (clientType === 'natural') {
                $validateBtn.show();
            } else {
                $validateBtn.hide();
                $validateResult.text('');
            }
        });

        // 触发初始化
        $('#id_client_type').trigger('change');

        // 绑定校验按钮点击事件
        $validateBtn.on('click', handleIdCardValidation);

        // 支持按回车键触发校验
        $idNumberField.on('keypress', function(e) {
            if (e.which === 13 && $('#id_client_type').val() === 'natural') {
                e.preventDefault();
                handleIdCardValidation();
            }
        });
    }

    /**
     * 处理身份证校验
     */
    function handleIdCardValidation() {
        var idNumber = $('#id_id_number').val().trim();
        var $validateResult = $('#id-card-validate-result');
        var $validateBtn = $('#id-card-validate-btn');

        if (!idNumber) {
            showValidateResult($validateResult, false, '请输入身份证号码');
            return;
        }

        // 显示加载状态
        $validateBtn.prop('disabled', true).text('校验中...');
        $validateResult.text('');

        // 调用校验 API
        $.ajax({
            url: '/api/v1/client/clients/validate-id-card',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            data: JSON.stringify({
                id_number: idNumber
            }),
            success: function(response) {
                showValidateResult($validateResult, response.valid, response.message);
            },
            error: function(xhr, status, error) {
                console.error('校验请求失败:', error);
                showValidateResult($validateResult, false, '校验请求失败，请检查网络连接');
            },
            complete: function() {
                $validateBtn.prop('disabled', false).text('校验');
            }
        });
    }

    /**
     * 显示校验结果
     */
    function showValidateResult($element, isValid, message) {
        var color = isValid ? '#4caf50' : '#f44336';
        var icon = isValid ? '✓' : '✗';
        $element.html('<span style="color: ' + color + ';">' + icon + ' ' + message + '</span>');
    }

    /**
     * 显示成功消息
     */
    function showSuccessMessage(message) {
        var $message = $('<div class="success-message" style="' +
            'position: fixed; top: 20px; right: 20px; ' +
            'background: #4caf50; color: white; padding: 15px 20px; ' +
            'border-radius: 4px; z-index: 10001; ' +
            'box-shadow: 0 2px 4px rgba(0,0,0,0.2);' +
            '">' + message + '</div>');

        $('body').append($message);

        // 3秒后自动消失
        setTimeout(function() {
            $message.fadeOut(function() {
                $message.remove();
            });
        }, 3000);
    }

    /**
     * 获取 CSRF Token
     */
    function getCsrfToken() {
        return $('[name=csrfmiddlewaretoken]').val() ||
               $('meta[name=csrf-token]').attr('content') ||
               document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    }

})(django.jQuery);
