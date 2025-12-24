/**
 * 客户 Admin 页面 JavaScript
 * 支持粘贴文本自动填充功能
 */

(function($) {
    'use strict';

    // 当页面加载完成时初始化
    $(document).ready(function() {
        initTextParsing();
        initFormEnhancements();
    });

    /**
     * 初始化文本解析功能
     */
    function initTextParsing() {
        // 添加"粘贴文本自动填充"按钮
        addParseTextButton();
        
        // 监听粘贴事件
        setupPasteListener();
    }

    /**
     * 添加"粘贴文本自动填充"按钮
     */
    function addParseTextButton() {
        // 只在添加页面显示按钮
        if (!window.location.pathname.includes('/add/')) {
            return;
        }

        var $submitRow = $('.submit-row');
        if ($submitRow.length === 0) {
            return;
        }

        // 创建按钮
        var $parseButton = $('<input type="button" value="粘贴文本自动填充" class="default" id="parse-text-btn">');
        
        // 添加到提交行
        $submitRow.prepend($parseButton);
        
        // 绑定点击事件
        $parseButton.on('click', showParseTextDialog);
    }

    /**
     * 显示文本解析对话框
     */
    function showParseTextDialog() {
        var dialogHtml = `
            <div id="parse-text-dialog" style="
                position: fixed; 
                top: 50%; 
                left: 50%; 
                transform: translate(-50%, -50%);
                background: white; 
                border: 2px solid #ccc; 
                padding: 20px; 
                z-index: 10000;
                width: 600px;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 4px 8px rgba(0,0,0,0.3);
            ">
                <h3>粘贴文本自动填充当事人信息</h3>
                <p>支持格式：</p>
                <ul style="font-size: 12px; color: #666; margin: 10px 0;">
                    <li>答辩人（被申请人）：广东XXX有限公司</li>
                    <li>原告：广东XXX发展有限公司</li>
                    <li>被告：徐X，男，汉族，1977年9月10日出生</li>
                </ul>
                <textarea id="parse-text-input" placeholder="请粘贴当事人信息..." style="
                    width: 100%; 
                    height: 200px; 
                    margin: 10px 0;
                    padding: 8px;
                    border: 1px solid #ccc;
                    font-family: monospace;
                "></textarea>
                <div style="margin: 10px 0;">
                    <label>
                        <input type="checkbox" id="parse-multiple-checkbox"> 
                        解析多个当事人（显示选择列表）
                    </label>
                </div>
                <div style="text-align: right;">
                    <button type="button" id="parse-text-cancel" style="margin-right: 10px;">取消</button>
                    <button type="button" id="parse-text-submit" class="default">解析并填充</button>
                </div>
            </div>
            <div id="parse-text-overlay" style="
                position: fixed; 
                top: 0; 
                left: 0; 
                width: 100%; 
                height: 100%; 
                background: rgba(0,0,0,0.5); 
                z-index: 9999;
            "></div>
        `;

        $('body').append(dialogHtml);

        // 绑定事件
        $('#parse-text-cancel, #parse-text-overlay').on('click', closeParseTextDialog);
        $('#parse-text-submit').on('click', handleParseText);
        
        // 聚焦到文本框
        $('#parse-text-input').focus();
    }

    /**
     * 关闭文本解析对话框
     */
    function closeParseTextDialog() {
        $('#parse-text-dialog, #parse-text-overlay').remove();
    }

    /**
     * 处理文本解析
     */
    function handleParseText() {
        var text = $('#parse-text-input').val().trim();
        var parseMultiple = $('#parse-multiple-checkbox').is(':checked');

        if (!text) {
            alert('请输入要解析的文本内容');
            return;
        }

        // 显示加载状态
        $('#parse-text-submit').prop('disabled', true).val('解析中...');

        // 调用解析 API
        $.ajax({
            url: '/api/v1/client/clients/parse-text',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            data: JSON.stringify({
                text: text,
                parse_multiple: parseMultiple
            }),
            success: function(response) {
                if (response.success) {
                    if (parseMultiple && response.clients) {
                        showMultipleParseResults(response.clients);
                    } else if (response.client) {
                        fillFormWithData(response.client);
                        closeParseTextDialog();
                        showSuccessMessage('文本解析成功，表单已自动填充');
                    }
                } else {
                    alert('解析失败: ' + (response.error || '未知错误'));
                }
            },
            error: function(xhr, status, error) {
                console.error('解析请求失败:', error);
                alert('解析请求失败，请检查网络连接');
            },
            complete: function() {
                $('#parse-text-submit').prop('disabled', false).val('解析并填充');
            }
        });
    }

    /**
     * 显示多个解析结果
     */
    function showMultipleParseResults(clients) {
        closeParseTextDialog();

        var resultsHtml = `
            <div id="multiple-results-dialog" style="
                position: fixed; 
                top: 50%; 
                left: 50%; 
                transform: translate(-50%, -50%);
                background: white; 
                border: 2px solid #ccc; 
                padding: 20px; 
                z-index: 10000;
                width: 700px;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 4px 8px rgba(0,0,0,0.3);
            ">
                <h3>解析结果 - 请选择要填充的当事人</h3>
                <div id="clients-list">
        `;

        clients.forEach(function(client, index) {
            var clientTypeDisplay = {
                'natural': '自然人',
                'legal': '法人',
                'non_legal_org': '非法人组织'
            }[client.client_type] || '自然人';

            resultsHtml += `
                <div style="border: 1px solid #ddd; margin: 10px 0; padding: 15px; background: #f9f9f9;">
                    <h4>当事人 ${index + 1}</h4>
                    <p><strong>姓名/名称：</strong>${client.name || ''}</p>
                    <p><strong>类型：</strong>${clientTypeDisplay}</p>
                    <p><strong>证件号码：</strong>${client.id_number || ''}</p>
                    <p><strong>地址：</strong>${client.address || ''}</p>
                    <p><strong>电话：</strong>${client.phone || ''}</p>
                    <p><strong>法定代表人：</strong>${client.legal_representative || ''}</p>
                    <p>
                        <button type="button" class="default select-client-btn" data-index="${index}">
                            选择此当事人
                        </button>
                    </p>
                </div>
            `;
        });

        resultsHtml += `
                </div>
                <div style="text-align: right; margin-top: 20px;">
                    <button type="button" id="multiple-results-cancel">取消</button>
                </div>
            </div>
            <div id="multiple-results-overlay" style="
                position: fixed; 
                top: 0; 
                left: 0; 
                width: 100%; 
                height: 100%; 
                background: rgba(0,0,0,0.5); 
                z-index: 9999;
            "></div>
        `;

        $('body').append(resultsHtml);

        // 绑定事件
        $('#multiple-results-cancel, #multiple-results-overlay').on('click', function() {
            $('#multiple-results-dialog, #multiple-results-overlay').remove();
        });

        $('.select-client-btn').on('click', function() {
            var index = $(this).data('index');
            var selectedClient = clients[index];
            
            fillFormWithData(selectedClient);
            $('#multiple-results-dialog, #multiple-results-overlay').remove();
            showSuccessMessage('已选择当事人信息并填充表单');
        });
    }

    /**
     * 用解析的数据填充表单
     */
    function fillFormWithData(data) {
        // 填充基本字段
        if (data.name) $('#id_name').val(data.name);
        if (data.phone) $('#id_phone').val(data.phone);
        if (data.address) $('#id_address').val(data.address);
        if (data.id_number) $('#id_id_number').val(data.id_number);
        if (data.legal_representative) $('#id_legal_representative').val(data.legal_representative);
        
        // 设置客户类型
        if (data.client_type) {
            $('#id_client_type').val(data.client_type).trigger('change');
        }

        // 触发字段变化事件以更新相关UI
        $('#id_client_type').trigger('change');
        
        // 高亮显示已填充的字段
        highlightFilledFields();
    }

    /**
     * 高亮显示已填充的字段
     */
    function highlightFilledFields() {
        var fields = ['#id_name', '#id_phone', '#id_address', '#id_id_number', '#id_legal_representative'];
        
        fields.forEach(function(fieldId) {
            var $field = $(fieldId);
            if ($field.val()) {
                $field.css({
                    'background-color': '#e8f5e8',
                    'border-color': '#4caf50'
                });
                
                // 3秒后恢复正常样式
                setTimeout(function() {
                    $field.css({
                        'background-color': '',
                        'border-color': ''
                    });
                }, 3000);
            }
        });
    }

    /**
     * 监听粘贴事件
     */
    function setupPasteListener() {
        // 在名称字段监听粘贴事件
        $('#id_name').on('paste', function(e) {
            setTimeout(function() {
                var pastedText = $('#id_name').val();
                
                // 如果粘贴的内容包含多行或特殊格式，提示用户使用解析功能
                if (pastedText && (pastedText.includes('\n') || pastedText.includes('：') || pastedText.includes(':'))) {
                    if (confirm('检测到您粘贴了格式化的当事人信息，是否使用自动解析功能？')) {
                        // 清空当前字段
                        $('#id_name').val('');
                        
                        // 显示解析对话框并预填充文本
                        showParseTextDialog();
                        setTimeout(function() {
                            $('#parse-text-input').val(pastedText);
                        }, 100);
                    }
                }
            }, 100);
        });
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