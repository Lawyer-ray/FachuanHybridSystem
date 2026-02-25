/**
 * 文书模板文件夹绑定内联编辑 - 树形选择器
 */
(function($) {
    'use strict';
    var folderStructureCache = {};

    $(document).ready(function() {
        console.log('[FolderBinding] 页面加载完成，开始初始化');

        // 延迟初始化，确保Django Admin的内联表单已完全渲染
        setTimeout(function() {
            console.log('[FolderBinding] 延迟初始化开始');
            initAllSelectors();
        }, 1200);

        // 监听添加新行的事件
        $(document).on('click', '.add-row a, tr.add-row a', function() {
            console.log('[FolderBinding] 检测到添加新行');
            setTimeout(initAllSelectors, 600);
        });

        // 监听内联表单集合的变化
        $(document).on('formset:added', function(event, $row) {
            console.log('[FolderBinding] 表单集合添加新行');
            setTimeout(initAllSelectors, 300);
        });
    });

    function initAllSelectors() {
        console.log('[FolderBinding] 开始初始化选择器');

        // Django Admin内联表单的字段命名模式：
        // - 字段名: documenttemplatefolderbinding_set-0-folder_node_id
        // - ID: id_documenttemplatefolderbinding_set-0-folder_node_id
        var selectors = [
            'input[name*="folder_node_id"]',
            'input[id*="folder_node_id"]'
        ];

        $(selectors.join(', ')).each(function() {
            var $nodeInput = $(this);
            var fieldName = $nodeInput.attr('name') || $nodeInput.attr('id') || 'unknown';
            console.log('[FolderBinding] 找到字段:', fieldName);

            if ($nodeInput.data('tree-init')) {
                console.log('[FolderBinding] 字段已初始化，跳过');
                return;
            }
            $nodeInput.data('tree-init', true);

            // 查找同一行的文件夹模板选择器
            var $row = $nodeInput.closest('tr, .form-row, .inline-related');
            var $templateSelect = $row.find('select[name*="folder_template"], select[id*="folder_template"]');

            console.log('[FolderBinding] 查找模板选择器:', $templateSelect.length);
            if ($templateSelect.length > 0) {
                console.log('[FolderBinding] 模板选择器字段:', $templateSelect.attr('name') || $templateSelect.attr('id'));
            }

            if ($templateSelect.length === 0) {
                console.log('[FolderBinding] 未找到模板选择器，跳过');
                return;
            }

            console.log('[FolderBinding] 创建树形选择器');
            createTreeSelector($nodeInput, $templateSelect);
        });
    }

    function createTreeSelector($nodeInput, $templateSelect) {
        console.log('[FolderBinding] 创建选择器，输入字段:', $nodeInput.attr('name'));
        console.log('[FolderBinding] 模板选择器:', $templateSelect.attr('name'));

        $nodeInput.hide();
        var $parent = $nodeInput.parent();
        if ($parent.find('.folder-selector-box').length > 0) {
            console.log('[FolderBinding] 选择器已存在，跳过');
            return;
        }

        var html = '<div class="folder-selector-box" style="display:inline-flex;align-items:center;gap:8px;">' +
            '<span class="folder-display" style="min-width:150px;padding:4px 8px;background:#f5f5f5;border:1px solid #ddd;border-radius:3px;font-size:13px;"><em style="color:#999;">请选择</em></span>' +
            '<button type="button" class="folder-btn" style="padding:4px 12px;background:#417690;color:#fff;border:none;border-radius:3px;cursor:pointer;font-size:13px;">选择文件夹</button>' +
            '<div class="folder-popup" style="display:none;position:absolute;z-index:9999;background:#fff;border:1px solid #ccc;border-radius:4px;box-shadow:0 2px 10px rgba(0,0,0,0.2);min-width:300px;max-height:350px;overflow-y:auto;padding:8px;margin-top:4px;"></div>' +
            '</div>';

        $nodeInput.after(html);
        var $box = $parent.find('.folder-selector-box');
        var $display = $box.find('.folder-display');
        var $btn = $box.find('.folder-btn');
        var $popup = $box.find('.folder-popup');

        console.log('[FolderBinding] 选择器HTML已插入');

        if ($nodeInput.val() && $templateSelect.val()) {
            loadPath($templateSelect.val(), $nodeInput.val(), $display);
        }

        $btn.on('click', function(e) {
            e.preventDefault();
            console.log('[FolderBinding] 点击选择按钮');
            // 重新获取当前行的模板选择器值（处理动态变化）
            var $currentRow = $(this).closest('tr, .form-row, .inline-related');
            var $currentTemplateSelect = $currentRow.find('select[name*="folder_template"], select[id*="folder_template"]');
            var tid = $currentTemplateSelect.val();
            console.log('[FolderBinding] 当前模板ID:', tid);
            if (!tid) {
                alert('请先选择文件夹模板');
                return;
            }
            $('.folder-popup').hide();
            loadTree(tid, $popup, $nodeInput, $display);
            $popup.show();
        });

        $templateSelect.on('change', function() {
            console.log('[FolderBinding] 模板选择器变更，当前值:', $(this).val());
            $nodeInput.val('');
            $display.html('<em style="color:#999;">请选择</em>');
            $popup.hide().empty();
        });

        $(document).on('click', function(e) {
            if (!$(e.target).closest('.folder-selector-box').length) $popup.hide();
        });
    }

    function loadTree(tid, $popup, $nodeInput, $display) {
        if (folderStructureCache[tid]) {
            renderTree(folderStructureCache[tid], $popup, $nodeInput, $display);
            return;
        }
        $popup.html('<div style="padding:15px;text-align:center;">加载中...</div>');
        $.get('/admin/documents/foldertemplate/' + tid + '/structure-json/', function(data) {
            if (data.success && data.structure) {
                folderStructureCache[tid] = data.structure;
                renderTree(data.structure, $popup, $nodeInput, $display);
            } else {
                $popup.html('<div style="padding:15px;color:#c00;">无数据</div>');
            }
        });
    }

    function renderTree(structure, $popup, $nodeInput, $display) {
        $popup.empty();
        var children = structure.children || [];
        if (!children.length) { $popup.html('<div style="padding:15px;">暂无文件夹</div>'); return; }
        renderNodes(children, $popup, '', $nodeInput, $display, $popup);
    }

    function renderNodes(nodes, $container, parentPath, $nodeInput, $display, $popup) {
        var $ul = $('<ul style="list-style:none;margin:0;padding:0;padding-left:' + (parentPath ? '16px' : '0') + ';"></ul>');
        nodes.forEach(function(node) {
            var path = parentPath ? parentPath + ' / ' + node.name : node.name;
            var hasKids = node.children && node.children.length > 0;
            var $li = $('<li style="margin:2px 0;"></li>');
            var $row = $('<div style="display:flex;align-items:center;padding:4px 6px;cursor:pointer;border-radius:3px;"></div>');
            var $toggle = $('<span style="width:14px;font-size:9px;color:#666;">' + (hasKids ? '▶' : '') + '</span>');
            var $name = $('<span style="flex:1;">📁 ' + node.name + '</span>');
            $row.append($toggle).append($name);
            if ($nodeInput.val() === node.id) $row.css({'background':'#e3f2fd','color':'#1565c0'});
            $row.hover(function(){ if($nodeInput.val()!==node.id) $(this).css('background','#f0f0f0'); },
                       function(){ if($nodeInput.val()!==node.id) $(this).css('background',''); });
            $name.on('click', function(e) {
                e.stopPropagation();
                $popup.find('div').css({'background':'','color':''});
                $row.css({'background':'#e3f2fd','color':'#1565c0'});
                $nodeInput.val(node.id);
                $display.html('<span style="color:#1565c0;">' + path + '</span>');
                setTimeout(function(){ $popup.hide(); }, 100);
            });
            $li.append($row);
            if (hasKids) {
                var $kids = $('<div style="display:none;"></div>');
                renderNodes(node.children, $kids, path, $nodeInput, $display, $popup);
                $li.append($kids);
                $toggle.css('cursor','pointer').on('click', function(e) {
                    e.stopPropagation();
                    var $k = $(this).closest('li').children('div:last');
                    if ($k.is(':visible')) { $k.slideUp(100); $(this).html('▶'); }
                    else { $k.slideDown(100); $(this).html('▼'); }
                });
            }
            $ul.append($li);
        });
        $container.append($ul);
    }

    function loadPath(tid, nodeId, $display) {
        if (folderStructureCache[tid]) {
            var p = findPath(folderStructureCache[tid].children || [], nodeId, '');
            if (p) $display.html('<span style="color:#1565c0;">' + p + '</span>');
            return;
        }
        $.get('/admin/documents/foldertemplate/' + tid + '/structure-json/', function(data) {
            if (data.success && data.structure) {
                folderStructureCache[tid] = data.structure;
                var p = findPath(data.structure.children || [], nodeId, '');
                if (p) $display.html('<span style="color:#1565c0;">' + p + '</span>');
            }
        });
    }

    function findPath(nodes, targetId, parentPath) {
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i], p = parentPath ? parentPath + ' / ' + n.name : n.name;
            if (n.id === targetId) return p;
            if (n.children && n.children.length) {
                var f = findPath(n.children, targetId, p);
                if (f) return f;
            }
        }
        return null;
    }
})(django.jQuery);
