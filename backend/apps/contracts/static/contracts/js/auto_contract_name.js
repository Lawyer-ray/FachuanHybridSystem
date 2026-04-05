/**
 * 合同名称自动生成功能
 * 规则：
 * 1. 必须选择至少1个当事人
 * 2. 单一当事人：当事人名称_合同类型+合同
 * 3. 多个当事人：同身份顿号分割，不同身份用"与"连接
 */
(function () {
    'use strict';

    // 等待页面加载完成
    function init() {
        var nameField = document.getElementById('id_name');
        if (!nameField) return;

        // 创建生成按钮（紧跟输入框后面，不重叠）
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'auto-contract-name-btn';
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>';
        btn.title = '自动生成合同名称';
        btn.style.cssText = [
            'display: inline-flex',
            'align-items: center',
            'justify-content: center',
            'background: #f8f9fa',
            'border: 1px solid #ddd',
            'cursor: pointer',
            'color: #666',
            'padding: 4px 6px',
            'border-radius: 4px',
            'margin-left: 4px',
            'vertical-align: middle',
            'line-height: 1',
            'transition: all 0.15s'
        ].join(';');

        // 鼠标悬停效果
        btn.addEventListener('mouseenter', function() {
            if (!btn.disabled) {
                btn.style.background = '#e8f4fd';
                btn.style.borderColor = '#447e9b';
                btn.style.color = '#447e9b';
            }
        });
        btn.addEventListener('mouseleave', function() {
            if (!btn.disabled) {
                btn.style.background = '#f8f9fa';
                btn.style.borderColor = '#ddd';
                btn.style.color = '#666';
            }
        });

        // 创建包装容器，把 input 和 button 并排显示
        var newWrapper = document.createElement('span');
        newWrapper.className = 'auto-name-wrapper';
        newWrapper.style.cssText = 'display:inline-flex; align-items:center; vertical-align:middle; white-space:nowrap;';
        
        // 把 input 移到新容器里
        nameField.parentNode.insertBefore(newWrapper, nameField);
        newWrapper.appendChild(nameField);
        
        // 把按钮放到新容器里（紧跟 input 后面）
        newWrapper.appendChild(btn);

        // 更新按钮状态
        updateButtonState(btn);

        // 点击事件
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            var generated = generateContractName();
            if (generated) {
                nameField.value = generated;
                // 触发change事件以便其他组件响应
                nameField.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });

        // 监听变化以更新按钮状态
        observeChanges(btn);
    }

    /**
     * 获取合同类型显示文本
     */
    function getCaseTypeLabel() {
        var select = document.getElementById('id_case_type');
        if (!select) return '';
        var option = select.options[select.selectedIndex];
        return option ? option.text : '';
    }

    /**
     * 获取所有已选择的当事人信息
     * @returns {Array<{name: string, role: string}>}
     */
    function getParties() {
        var parties = [];

        // 遍历所有当事人行的隐藏 select 元素
        // select2 会隐藏原始 select 并在旁边创建 .select2-container
        var allSelects = document.querySelectorAll('select');
        
        allSelects.forEach(function (select) {
            var id = select.id || '';
            // 只处理当事人 client 字段（两种命名格式）
            if (!id.match(/contract_parties-\d+-client$/) &&
                !id.match(/contractparty_set-\d+-client$/)) return;

            // 检查是否有值被选中
            var name = '';
            var value = select.value;

            // 方法1: 直接从 option 获取文本
            if (value && select.options && select.selectedIndex >= 0) {
                name = select.options[select.selectedIndex].text || '';
            }

            // 方法2: 从旁边的 select2 容器获取显示的文本
            if (!name) {
                var s2Container = null;
                // select2 容器通常紧跟在 hidden select 后面
                var sibling = select.nextElementSibling;
                while (sibling) {
                    if (sibling.classList && (
                        sibling.classList.contains('select2-container') ||
                        sibling.tagName === 'SPAN'
                    )) {
                        s2Container = sibling;
                        break;
                    }
                    sibling = sibling.nextSibling;
                }
                
                if (s2Container && s2Container.classList.contains('select2-container')) {
                    var rendered = s2Container.querySelector('.select2-selection__rendered') ||
                                   s2Container.querySelector('[class*="rendered"]');
                    if (rendered) {
                        var txt = ((rendered.textContent || '') + ' ' + (rendered.innerText || '')).trim();
                        // 排除 placeholder
                        if (txt && !rendered.classList.contains('select2-placeholder') &&
                            txt.length > 0 && txt !== '--------' && txt !== 'None') {
                            name = txt;
                            // 同时用这个值作为 fallback value
                            if (!value) value = txt;
                        }
                    }
                }
            }

            // 方法3: 如果都没有，用 value 本身
            if (!name && value) name = value;

            if (!name) return; // 没有选择任何当事人

            // 找到对应的角色字段
            var prefix = id.replace(/-client$/, '');
            var roleEl = document.getElementById(prefix + '-role');

            var role = 'PRINCIPAL'; // 默认
            if (roleEl) {
                // 角色 select 可能也是 select2
                role = roleEl.value;
                if (!role) {
                    var roleS2 = roleEl.nextElementSibling;
                    if (roleS2 && roleS2.classList.contains('select2-container')) {
                        var rText = roleS2.querySelector('.select2-selection__rendered');
                        if (rText) {
                            role = (rText.textContent || rText.innerText || '').trim() || 'PRINCIPAL';
                        }
                    }
                }
                // 如果获取到的是中文，映射回英文值
                if (role === '委托人') role = 'PRINCIPAL';
                else if (role === '受益人') role = 'BENEFICIARY';
                else if (role === '对方当事人') role = 'OPPOSING';
            }

            parties.push({ name: name, role: role });
        });

        return parties;
    }

    /**
     * 生成合同名称
     */
    function generateContractName() {
        var parties = getParties();
        if (parties.length === 0) {
            return null; // 没有当事人
        }

        var caseTypeLabel = getCaseTypeLabel();
        if (!caseTypeLabel) return null;

        // 按角色分组
        var groups = {};
        parties.forEach(function (p) {
            if (!groups[p.role]) groups[p.role] = [];
            groups[p.role].push(p.name);
        });

        // 构建各组的名称字符串
        var groupNames = [];
        
        // PRINCIPAL(委托人) 排第一，BENEFICIARY(受益人) 第二，OPPOSING(对方当事人) 最后
        var order = ['PRINCIPAL', 'BENEFICIARY', 'OPPOSING'];
        order.forEach(function (role) {
            if (groups[role] && groups[role].length > 0) {
                groupNames.push(groups[role].join('、'));
            }
        });

        // 组合：不同组之间用"与"连接
        var partiesStr = groupNames.join('与');

        return partiesStr + '_' + caseTypeLabel + '合同';
    }

    /**
     * 更新按钮状态
     */
    function updateButtonState(btn) {
        var parties = getParties();
        var caseType = getCaseTypeLabel();

        var canGenerate = parties.length > 0 && caseType.length > 0;

        btn.disabled = !canGenerate;
        if (!canGenerate) {
            btn.style.background = '#f5f5f5';
            btn.style.borderColor = '#eee';
            btn.style.color = '#ccc';
            btn.style.cursor = 'not-allowed';
        } else {
            btn.style.background = '#f8f9fa';
            btn.style.borderColor = '#ddd';
            btn.style.color = '#666';
            btn.style.cursor = 'pointer';
        }

        if (!canGenerate) {
            if (parties.length === 0) {
                btn.title = '请先选择至少一个当事人';
            } else {
                btn.title = '请先选择合同类型';
            }
        } else {
            btn.title = '自动生成合同名称';
        }
    }

    /**
     * 监听表单变化
     */
    function observeChanges(btn) {
        // 使用 MutationObserver 监听 DOM 变化（用于动态添加的内联行）
        var observer = new MutationObserver(function () {
            updateButtonState(btn);
        });

        var inlineGroup = document.getElementById('contract_parties-group') ||
                          document.getElementById('contractparty_set-group');
        if (inlineGroup) {
            observer.observe(inlineGroup, { childList: true, subtree: true });
        }

        // 监听合同类型变化
        var caseTypeSelect = document.getElementById('id_case_type');
        if (caseTypeSelect) {
            caseTypeSelect.addEventListener('change', function () {
                updateButtonState(btn);
            });
        }

        // 使用事件委托监听当事人选择和角色变化
        document.addEventListener('change', function (e) {
            var target = e.target;
            var id = (target.id || '') + ' ' + (target.name || '');
            if (
                id.match(/contract_parties.*client/) ||
                id.match(/contract_parties.*role/) ||
                id.match(/contractparty_set.*client/) ||
                id.match(/contractparty_set.*role/)
            ) {
                setTimeout(function () { updateButtonState(btn); }, 150);
            }
        });

        // 监听 select2 选择事件（当事人用 autocomplete_fields）
        if (typeof $ !== 'undefined') {
            $(document).on('select2:select change', function(e) {
                var elId = e.target ? e.target.id : '';
                if (
                    elId.match(/contract_parties/) ||
                    elId.match(/contractparty_set/)
                ) {
                    setTimeout(function() { updateButtonState(btn); }, 150);
                }
            });
            
            // 同时监听 select2 容器上的事件
            $(document).on('change', '.select2-container', function() {
                setTimeout(function() { updateButtonState(btn); }, 150);
            });
        }
    }

    // DOM 加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
