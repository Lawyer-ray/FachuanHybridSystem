(function($) {
    'use strict';

    $(document).ready(function() {
        var contractField = $('#id_contract');
        var caseField = $('#id_case');

        if (!contractField.length || !caseField.length) {
            return;
        }

        // 当合同改变时，通过 AJAX 重新加载案件列表
        contractField.on('change', function() {
            var contractId = $(this).val();

            if (!contractId) {
                // 清空案件选择
                caseField.find('option').remove();
                caseField.append($('<option></option>').attr('value', '').text('---------'));
                return;
            }

            // 保存当前选中的案件
            var selectedCase = caseField.val();

            // 通过 AJAX 获取该合同的案件
            $.ajax({
                url: '/admin/contracts/clientpaymentrecord/get-cases-by-contract/',
                method: 'GET',
                data: { contract_id: contractId },
                success: function(response) {
                    // 清空下拉框
                    caseField.find('option').remove();

                    // 添加空选项
                    caseField.append($('<option></option>').attr('value', '').text('---------'));

                    // 添加新的案件选项
                    if (response.cases && response.cases.length > 0) {
                        response.cases.forEach(function(caseItem) {
                            var option = $('<option></option>')
                                .attr('value', caseItem.id)
                                .text(caseItem.name);

                            // 如果之前已选择且仍在列表中，保持选中
                            if (String(caseItem.id) === String(selectedCase)) {
                                option.attr('selected', 'selected');
                            }

                            caseField.append(option);
                        });
                    }
                },
                error: function(xhr, status, error) {
                    console.error('Failed to load cases:', error);
                }
            });
        });
    });
})(django.jQuery);
