/**
 * 诉讼费用计算器
 *
 * 监听涉案金额和财产保全金额字段变化，自动调用 API 计算并显示费用。
 * 使用防抖机制避免频繁调用 API。
 */
(function() {
    'use strict';

    // 配置
    const CONFIG = {
        API_URL: '/api/v1/cases/calculate-fee',
        DEBOUNCE_DELAY: 300,  // 防抖延迟（毫秒）
        TARGET_AMOUNT_FIELD: 'id_target_amount',
        PRESERVATION_AMOUNT_FIELD: 'id_preservation_amount',
        CASE_TYPE_FIELD: 'id_case_type',
        CAUSE_OF_ACTION_FIELD: 'id_cause_of_action',  // 案由字段ID
    };

    // 防抖函数
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // 格式化金额显示
    function formatCurrency(amount) {
        if (amount === null || amount === undefined) {
            return '-';
        }
        return amount.toLocaleString('zh-CN', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }) + ' 元';
    }

    // 创建或获取费用显示容器
    function getOrCreateFeeDisplay(fieldId, label) {
        const containerId = fieldId + '_fee_display';
        let container = document.getElementById(containerId);

        if (!container) {
            const field = document.getElementById(fieldId);
            if (!field) return null;

            container = document.createElement('div');
            container.id = containerId;
            container.className = 'litigation-fee-display';
            container.style.cssText = 'margin-top: 5px; padding: 8px 12px; background: #f8f9fa; border-radius: 4px; font-size: 13px; color: #495057;';

            // 插入到字段后面
            const fieldWrapper = field.closest('.form-row') || field.parentElement;
            if (fieldWrapper) {
                fieldWrapper.appendChild(container);
            }
        }

        return container;
    }

    // 更新费用显示
    function updateFeeDisplay(result) {
        // 涉案金额相关费用
        const targetDisplay = getOrCreateFeeDisplay(CONFIG.TARGET_AMOUNT_FIELD, '案件受理费');
        if (targetDisplay) {
            let html = '';

            // 特殊案件类型：显示特殊费用文本
            if (result.special_case_type && result.fee_display_text) {
                html += `<div><strong>${result.fee_display_text}</strong></div>`;

                // 如果有费用范围，显示范围
                if (result.fee_range_min !== null && result.fee_range_max !== null) {
                    if (result.fee_range_min !== result.fee_range_max) {
                        // 范围显示
                        const halfMin = result.fee_range_min / 2;
                        const halfMax = result.fee_range_max / 2;
                        if (result.show_half_fee) {
                            html += `<div style="color: #6c757d; font-size: 12px;">减半后受理费：${halfMin.toFixed(2)}-${halfMax.toFixed(2)}元</div>`;
                        }
                    } else {
                        // 精确费用
                        if (result.show_acceptance_fee && result.acceptance_fee !== null) {
                            html = `<div><strong>案件受理费：</strong>${formatCurrency(result.acceptance_fee)}</div>`;
                        }
                        if (result.show_half_fee && result.acceptance_fee_half !== null) {
                            html += `<div><strong>减半后受理费：</strong>${formatCurrency(result.acceptance_fee_half)}</div>`;
                        }
                    }
                }

                // 支付令案件：显示支付令申请费
                if (result.show_payment_order_fee && result.payment_order_fee !== null) {
                    html += `<div><strong>支付令申请费：</strong>${formatCurrency(result.payment_order_fee)}</div>`;
                }
            }
            // 固定费用类型
            else if (result.fixed_fee !== null && result.fixed_fee !== undefined) {
                html += `<div><strong>${result.fee_name || '案件受理费'}：</strong>${formatCurrency(result.fixed_fee)}</div>`;
            }
            // 财产案件受理费
            else if (result.acceptance_fee !== null && result.acceptance_fee !== undefined) {
                if (result.show_acceptance_fee !== false) {
                    html += `<div><strong>案件受理费：</strong>${formatCurrency(result.acceptance_fee)}</div>`;
                }
                if (result.show_half_fee !== false) {
                    html += `<div><strong>减半后受理费：</strong>${formatCurrency(result.acceptance_fee_half)}</div>`;
                }
                if (result.show_payment_order_fee && result.payment_order_fee !== null) {
                    html += `<div><strong>支付令申请费：</strong>${formatCurrency(result.payment_order_fee)}</div>`;
                }
            }
            // 执行案件费用
            else if (result.execution_fee !== null && result.execution_fee !== undefined) {
                html += `<div><strong>执行案件费用：</strong>${formatCurrency(result.execution_fee)}</div>`;
            }
            // 破产案件费用
            else if (result.bankruptcy_fee !== null && result.bankruptcy_fee !== undefined) {
                html += `<div><strong>破产案件费用：</strong>${formatCurrency(result.bankruptcy_fee)}</div>`;
            }
            // 离婚案件费用
            else if (result.divorce_fee !== null && result.divorce_fee !== undefined) {
                html += `<div><strong>离婚案件费用：</strong>${formatCurrency(result.divorce_fee)}</div>`;
            }
            // 人格权案件费用
            else if (result.personality_rights_fee !== null && result.personality_rights_fee !== undefined) {
                html += `<div><strong>人格权侵权案件费用：</strong>${formatCurrency(result.personality_rights_fee)}</div>`;
            }
            // 知识产权案件费用
            else if (result.ip_fee !== null && result.ip_fee !== undefined) {
                html += `<div><strong>知识产权案件费用：</strong>${formatCurrency(result.ip_fee)}</div>`;
            }
            // 支付令申请费（单独显示）
            else if (result.payment_order_fee !== null && result.payment_order_fee !== undefined) {
                html += `<div><strong>支付令申请费：</strong>${formatCurrency(result.payment_order_fee)}</div>`;
            }

            targetDisplay.innerHTML = html || '<div style="color: #6c757d;">请输入涉案金额</div>';
        }

        // 财产保全费
        const preservationDisplay = getOrCreateFeeDisplay(CONFIG.PRESERVATION_AMOUNT_FIELD, '财产保全费');
        if (preservationDisplay) {
            if (result.preservation_fee !== null && result.preservation_fee !== undefined) {
                preservationDisplay.innerHTML = `<div><strong>财产保全费：</strong>${formatCurrency(result.preservation_fee)}</div>`;
            } else {
                preservationDisplay.innerHTML = '<div style="color: #6c757d;">请输入财产保全金额</div>';
            }
        }
    }

    // 显示错误信息
    function showError(message) {
        const targetDisplay = getOrCreateFeeDisplay(CONFIG.TARGET_AMOUNT_FIELD, '');
        if (targetDisplay) {
            targetDisplay.innerHTML = `<div style="color: #dc3545;">${message}</div>`;
        }
    }

    // 获取案由ID
    function getCauseOfActionId() {
        const causeField = document.getElementById(CONFIG.CAUSE_OF_ACTION_FIELD);
        return causeField ? parseInt(causeField.value) || null : null;
    }

    // 调用 API 计算费用
    async function calculateFees() {
        const targetAmountField = document.getElementById(CONFIG.TARGET_AMOUNT_FIELD);
        const preservationAmountField = document.getElementById(CONFIG.PRESERVATION_AMOUNT_FIELD);
        const caseTypeField = document.getElementById(CONFIG.CASE_TYPE_FIELD);

        const targetAmount = targetAmountField ? parseFloat(targetAmountField.value) || null : null;
        const preservationAmount = preservationAmountField ? parseFloat(preservationAmountField.value) || null : null;
        const caseType = caseTypeField ? caseTypeField.value || null : null;
        const causeOfActionId = getCauseOfActionId();

        // 如果两个金额都为空且没有案由ID，不调用 API
        if (targetAmount === null && preservationAmount === null && causeOfActionId === null) {
            updateFeeDisplay({
                acceptance_fee: null,
                acceptance_fee_half: null,
                preservation_fee: null,
                execution_fee: null,
                payment_order_fee: null,
                bankruptcy_fee: null,
            });
            return;
        }

        try {
            const response = await fetch(CONFIG.API_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '',
                },
                body: JSON.stringify({
                    target_amount: targetAmount,
                    preservation_amount: preservationAmount,
                    case_type: caseType,
                    cause_of_action_id: causeOfActionId,
                }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '计算失败');
            }

            const result = await response.json();
            updateFeeDisplay(result);
        } catch (error) {
            console.error('费用计算失败:', error);
            showError('计算服务暂时不可用');
        }
    }

    // 带防抖的计算函数
    const debouncedCalculate = debounce(calculateFees, CONFIG.DEBOUNCE_DELAY);

    // 初始化
    function init() {
        // 监听涉案金额字段
        const targetAmountField = document.getElementById(CONFIG.TARGET_AMOUNT_FIELD);
        if (targetAmountField) {
            targetAmountField.addEventListener('input', debouncedCalculate);
            targetAmountField.addEventListener('change', debouncedCalculate);
        }

        // 监听财产保全金额字段
        const preservationAmountField = document.getElementById(CONFIG.PRESERVATION_AMOUNT_FIELD);
        if (preservationAmountField) {
            preservationAmountField.addEventListener('input', debouncedCalculate);
            preservationAmountField.addEventListener('change', debouncedCalculate);
        }

        // 监听案件类型字段
        const caseTypeField = document.getElementById(CONFIG.CASE_TYPE_FIELD);
        if (caseTypeField) {
            caseTypeField.addEventListener('change', debouncedCalculate);
        }

        // 监听案由字段
        const causeOfActionField = document.getElementById(CONFIG.CAUSE_OF_ACTION_FIELD);
        if (causeOfActionField) {
            causeOfActionField.addEventListener('change', debouncedCalculate);
        }

        // 初始计算
        if (targetAmountField || preservationAmountField || causeOfActionField) {
            calculateFees();
        }
    }

    // DOM 加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
