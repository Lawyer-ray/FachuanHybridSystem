/**
 * 证据清单类型动态更新
 *
 * 当案件选择变化时，自动获取并显示下一个清单类型
 */
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        const caseField = document.getElementById('id_case');
        const listTypeField = document.querySelector('.field-list_type .readonly');

        if (!caseField) {
            console.log('[evidence_list_type] 案件字段不存在');
            return;
        }

        // 检查是否是新建页面（编辑页面不需要动态更新）
        const isAddPage = window.location.pathname.includes('/add/');
        if (!isAddPage) {
            console.log('[evidence_list_type] 编辑页面，跳过动态更新');
            return;
        }

        console.log('[evidence_list_type] 初始化动态清单类型');

        // 监听案件选择变化
        caseField.addEventListener('change', function() {
            const caseId = this.value;
            console.log('[evidence_list_type] 案件变化:', caseId);

            if (!caseId) {
                updateListTypeDisplay('-', '请先选择案件');
                return;
            }

            fetchNextListType(caseId);
        });

        // 页面加载时，如果已有案件选择，获取清单类型
        if (caseField.value) {
            fetchNextListType(caseField.value);
        }
    });

    function fetchNextListType(caseId) {
        const url = `/admin/documents/evidencelist/next-list-type/${caseId}/`;

        fetch(url, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            console.log('[evidence_list_type] 响应:', data);

            if (data.success) {
                updateListTypeDisplay(data.label, '系统自动分配');
            } else {
                updateListTypeDisplay('无法创建', data.error);
            }
        })
        .catch(error => {
            console.error('[evidence_list_type] 请求失败:', error);
            updateListTypeDisplay('加载失败', '请刷新页面重试');
        });
    }

    function updateListTypeDisplay(label, helpText) {
        // 更新只读字段显示
        const listTypeReadonly = document.querySelector('.field-list_type .readonly');
        if (listTypeReadonly) {
            listTypeReadonly.textContent = label;
        }

        // 同时更新标题字段（如果存在）
        const titleReadonly = document.querySelector('.field-title .readonly');
        if (titleReadonly) {
            titleReadonly.textContent = label;
        }
    }
})();
