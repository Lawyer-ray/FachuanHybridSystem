/**
 * 文书模板文件夹绑定 Admin JS
 * 用于独立的绑定编辑页面
 */
(function() {
    'use strict';

    // 等待 django.jQuery 可用
    function init() {
        if (typeof django === 'undefined' || typeof django.jQuery === 'undefined') {
            setTimeout(init, 100);
            return;
        }

        var $ = django.jQuery;

        $(document).ready(function() {
            var folderTemplateSelect = $('#id_folder_template');
            var folderNodeSelect = $('#id_folder_node_id');

            if (!folderTemplateSelect.length || !folderNodeSelect.length) {
                return;
            }

            folderTemplateSelect.on('change', function() {
                var templateId = $(this).val();
                if (!templateId) {
                    folderNodeSelect.html('<option value="">---------</option>');
                    return;
                }
                loadFolderNodes(templateId);
            });

            function loadFolderNodes(templateId) {
                folderNodeSelect.html('<option value="">加载中...</option>');
                folderNodeSelect.prop('disabled', true);

                $.ajax({
                    url: '/admin/documents/foldertemplate/' + templateId + '/structure-json/',
                    method: 'GET',
                    dataType: 'json',
                    success: function(data) {
                        if (data.success && data.structure) {
                            var options = extractNodes(data.structure.children || [], '');
                            var optionsHtml = '<option value="">---------</option>';
                            options.forEach(function(opt) {
                                optionsHtml += '<option value="' + opt.id + '">' + opt.name + '</option>';
                            });
                            folderNodeSelect.html(optionsHtml);
                        } else {
                            folderNodeSelect.html('<option value="">无可用节点</option>');
                        }
                        folderNodeSelect.prop('disabled', false);
                    },
                    error: function() {
                        folderNodeSelect.html('<option value="">加载失败</option>');
                        folderNodeSelect.prop('disabled', false);
                    }
                });
            }

            function extractNodes(children, prefix) {
                var nodes = [];
                children.forEach(function(child) {
                    var nodeId = child.id || '';
                    var nodeName = child.name || '';
                    var displayName = prefix ? prefix + ' / ' + nodeName : nodeName;
                    if (nodeId) {
                        nodes.push({ id: nodeId, name: displayName });
                    }
                    if (child.children && child.children.length > 0) {
                        var subNodes = extractNodes(child.children, displayName);
                        nodes.push.apply(nodes, subNodes);
                    }
                });
                return nodes;
            }
        });
    }

    init();
})();
