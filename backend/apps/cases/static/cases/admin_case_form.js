/**
 * 案件 Admin 表单动态过滤脚本
 * 
 * 功能：
 * 1. 根据案件类型显示/隐藏相关字段
 * 2. 当案件绑定合同时，动态过滤 CaseParty inline 的 client 选择框
 * 
 * Requirements: 3.1, 3.2, 3.3, 3.4
 */
;(function(){
  // ============================================================
  // 工具函数
  // ============================================================
  function byId(id){return document.getElementById(id)}
  function fieldDivs(name){return document.querySelectorAll('div.field-' + name)}
  function selectsByNameSuffix(suffix){return document.querySelectorAll('select[name$="' + suffix + '"]')}
  function inputsByNameSuffix(suffix){return document.querySelectorAll('input[name$="' + suffix + '"]')}

  // ============================================================
  // 案件类型相关字段显示/隐藏逻辑
  // ============================================================
  function toggle(){
    var sel = byId('id_case_type')
    if(!sel) return
    var v = (sel.value || '').toLowerCase().trim()
    var allowed = new Set(['civil','criminal','administrative','labor','intl'])
    var show = allowed.has(v)
    fieldDivs('current_stage').forEach(function(div){ div.style.display = '' })
    fieldDivs('cause_of_action').forEach(function(div){ div.style.display = '' })
    inputsByNameSuffix('cause_of_action').forEach(function(inp){
      if(!inp.value || inp.value.trim() === ''){ inp.value = '合同纠纷' }
    })
    if(!show){
      selectsByNameSuffix('current_stage').forEach(function(cur){ cur.value='' })
    }
  }

  // ============================================================
  // 合同当事人动态过滤逻辑
  // Requirements: 3.1, 3.2, 3.3, 3.4
  // ============================================================
  
  // 缓存所有客户选项（用于恢复）
  var allClientOptions = null;
  // 缓存合同当事人数据
  var contractPartiesCache = {};
  // 当前加载状态
  var isLoading = false;

  /**
   * 获取所有 CaseParty inline 的 client 选择框
   * 优先使用 CSS 类选择器，兼容旧版选择器
   */
  function getClientSelects() {
    // 优先使用带有特定 CSS 类的选择框
    var selects = document.querySelectorAll(
      'select.contract-party-client-select, ' +
      'select[data-contract-party-filter="true"]'
    );
    
    // 如果没有找到，使用兼容选择器
    if (selects.length === 0) {
      selects = document.querySelectorAll(
        'select[name$="-client"], ' +
        '#caseparty_set-group select[id$="-client"]'
      );
    }
    
    return selects;
  }

  /**
   * 保存所有客户选项（首次加载时）
   */
  function saveAllClientOptions() {
    if (allClientOptions !== null) return;
    
    var selects = getClientSelects();
    if (selects.length === 0) return;
    
    var firstSelect = selects[0];
    allClientOptions = [];
    
    for (var i = 0; i < firstSelect.options.length; i++) {
      var opt = firstSelect.options[i];
      allClientOptions.push({
        value: opt.value,
        text: opt.text
      });
    }
  }

  /**
   * 设置选择框的加载状态
   * Requirements: 3.4
   */
  function setLoadingState(loading) {
    isLoading = loading;
    var selects = getClientSelects();
    
    // 更新 inline 容器的过滤状态类
    var inlineGroup = document.querySelector('.contract-party-inline, #caseparty_set-group');
    if (inlineGroup) {
      if (loading) {
        inlineGroup.classList.add('contract-party-loading-state');
      } else {
        inlineGroup.classList.remove('contract-party-loading-state');
      }
    }
    
    selects.forEach(function(select) {
      select.disabled = loading;
      
      // 更新加载提示
      var wrapper = select.closest('td') || select.parentElement;
      var loadingIndicator = wrapper.querySelector('.contract-party-loading');
      
      if (loading) {
        if (!loadingIndicator) {
          loadingIndicator = document.createElement('span');
          loadingIndicator.className = 'contract-party-loading';
          loadingIndicator.style.cssText = 'margin-left: 8px; color: #666; font-size: 12px;';
          loadingIndicator.textContent = '加载中...';
          wrapper.appendChild(loadingIndicator);
        }
      } else {
        if (loadingIndicator) {
          loadingIndicator.remove();
        }
      }
    });
  }

  /**
   * 更新选择框选项
   * @param {Array} parties - 当事人列表 [{id, name, source}, ...]
   * Requirements: 3.2
   */
  function updateClientOptions(parties) {
    var selects = getClientSelects();
    
    selects.forEach(function(select) {
      var currentValue = select.value;
      
      // 清空现有选项（保留空选项）
      while (select.options.length > 1) {
        select.remove(1);
      }
      
      // 添加新选项
      parties.forEach(function(party) {
        var opt = document.createElement('option');
        opt.value = party.id;
        // 显示来源标识
        var sourceLabel = party.source === 'contract' ? '[合同]' : '[补充协议]';
        opt.text = party.name + ' ' + sourceLabel;
        select.appendChild(opt);
      });
      
      // 尝试恢复之前选中的值
      if (currentValue) {
        var found = false;
        for (var i = 0; i < select.options.length; i++) {
          if (select.options[i].value === currentValue) {
            select.value = currentValue;
            found = true;
            break;
          }
        }
        // 如果之前选中的值不在新列表中，清空选择
        if (!found) {
          select.value = '';
        }
      }
    });
  }

  /**
   * 恢复所有客户选项
   * Requirements: 3.3
   */
  function restoreAllClientOptions() {
    if (!allClientOptions) return;
    
    var selects = getClientSelects();
    
    selects.forEach(function(select) {
      var currentValue = select.value;
      
      // 清空现有选项
      select.innerHTML = '';
      
      // 恢复所有选项
      allClientOptions.forEach(function(opt) {
        var option = document.createElement('option');
        option.value = opt.value;
        option.text = opt.text;
        select.appendChild(option);
      });
      
      // 恢复之前选中的值
      if (currentValue) {
        select.value = currentValue;
      }
    });
  }

  /**
   * 从 API 获取合同当事人
   * @param {string} contractId - 合同 ID
   * Requirements: 3.1
   */
  function fetchContractParties(contractId) {
    // 防止重复请求
    if (isLoading) return;
    
    // 检查缓存
    if (contractPartiesCache[contractId]) {
      updateClientOptions(contractPartiesCache[contractId]);
      return;
    }
    
    setLoadingState(true);
    
    var url = '/api/v1/contracts/contracts/' + contractId + '/all-parties';
    
    fetch(url)
      .then(function(response) {
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }
        return response.json();
      })
      .then(function(parties) {
        // 缓存结果
        contractPartiesCache[contractId] = parties;
        // 更新选项
        updateClientOptions(parties);
      })
      .catch(function(error) {
        console.error('获取合同当事人失败:', error);
        // 出错时恢复所有选项
        restoreAllClientOptions();
      })
      .finally(function() {
        setLoadingState(false);
      });
  }

  /**
   * 处理合同字段变化
   * Requirements: 3.1, 3.2, 3.3
   */
  function handleContractChange() {
    var contractSelect = byId('id_contract');
    if (!contractSelect) return;
    
    var contractId = contractSelect.value;
    
    // 更新 inline 容器的过滤激活状态
    var inlineGroup = document.querySelector('.contract-party-inline, #caseparty_set-group');
    if (inlineGroup) {
      if (contractId) {
        inlineGroup.classList.add('contract-party-filter-active');
      } else {
        inlineGroup.classList.remove('contract-party-filter-active');
      }
    }
    
    if (contractId) {
      // 有合同，获取合同当事人并过滤
      fetchContractParties(contractId);
    } else {
      // 无合同，恢复所有客户选项
      restoreAllClientOptions();
    }
  }

  /**
   * 初始化合同当事人过滤功能
   */
  function initContractPartyFilter() {
    var contractSelect = byId('id_contract');
    if (!contractSelect) return;
    
    // 保存所有客户选项
    saveAllClientOptions();
    
    // 监听合同字段变化
    contractSelect.addEventListener('change', handleContractChange);
    
    // 初始化时检查是否已有合同
    if (contractSelect.value) {
      handleContractChange();
    }
  }

  /**
   * 处理新增 inline 行时的选项同步
   */
  function handleInlineAdded() {
    var contractSelect = byId('id_contract');
    if (!contractSelect || !contractSelect.value) {
      // 无合同，使用所有选项
      return;
    }
    
    var contractId = contractSelect.value;
    if (contractPartiesCache[contractId]) {
      // 有缓存，直接更新新行的选项
      updateClientOptions(contractPartiesCache[contractId]);
    }
  }

  // ============================================================
  // 初始化
  // ============================================================
  document.addEventListener('DOMContentLoaded', function(){
    // 案件类型字段逻辑
    var sel = byId('id_case_type')
    if(sel){
      sel.addEventListener('change', toggle)
      toggle()
    }
    
    // 合同当事人过滤逻辑
    initContractPartyFilter();
    
    // 监听 inline 行添加事件（Django Admin 使用 formset:added 事件）
    document.body.addEventListener('formset:added', function(e) {
      if (e.detail && e.detail[0]) {
        var row = e.detail[0];
        if (row.classList && row.classList.contains('dynamic-caseparty_set')) {
          // 延迟执行，确保 DOM 已更新
          setTimeout(handleInlineAdded, 100);
        }
      }
    });
  });
  
})();
