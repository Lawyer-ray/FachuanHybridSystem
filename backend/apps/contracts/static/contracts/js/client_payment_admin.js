(function($) {
    'use strict';
    
    $(document).ready(function() {
        var contractField = $('#id_contract');
        var casesFromBox = $('#id_cases_from');
        var casesToBox = $('#id_cases_to');
        
        if (!contractField.length || !casesFromBox.length) {
            return;
        }
        
        // 保存所有案件选项（包括 contract_id 信息）
        var allCasesData = {};
        
        // 从页面加载时获取所有案件及其合同关系
        function loadAllCases() {
            casesFromBox.find('option').each(function() {
                var caseId = $(this).val();
                var caseName = $(this).text();
                // 从 option 的 text 中提取合同信息（如果有的话）
                // 或者通过 AJAX 获取
                allCasesData[caseId] = {
                    id: caseId,
                    name: caseName
                };
            });
        }
        
        loadAllCases();
        
        // 当合同改变时，通过 AJAX 重新加载案件列表
        contractField.on('change', function() {
            var contractId = $(this).val();
            
            if (!contractId) {
                // 清空案件选择
                casesFromBox.find('option').remove();
                casesToBox.find('option').remove();
                return;
            }
            
            // 通过 AJAX 获取该合同的案件
            $.ajax({
                url: '/admin/contracts/clientpaymentrecord/get-cases-by-contract/',
                method: 'GET',
                data: { contract_id: contractId },
                success: function(response) {
                    // 保存当前已选择的案件
                    var selectedCases = [];
                    casesToBox.find('option').each(function() {
                        selectedCases.push($(this).val());
                    });
                    
                    // 清空两个选择框
                    casesFromBox.find('option').remove();
                    casesToBox.find('option').remove();
                    
                    // 添加新的案件选项
                    if (response.cases && response.cases.length > 0) {
                        response.cases.forEach(function(caseItem) {
                            var option = $('<option></option>')
                                .attr('value', caseItem.id)
                                .text(caseItem.name);
                            
                            // 如果之前已选择，放到右边
                            if (selectedCases.indexOf(String(caseItem.id)) !== -1) {
                                casesToBox.append(option);
                            } else {
                                casesFromBox.append(option);
                            }
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
