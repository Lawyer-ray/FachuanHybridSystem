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
  // 自动填充进行中标志（防止 handleInlineAdded 干扰）
  var isAutoFilling = false;

  /**
   * 获取所有 CaseParty inline 的 client 选择框
   * 优先使用 CSS 类选择器，兼容旧版选择器
   * 排除模板行（__prefix__）
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
    
    // 过滤掉模板行（name 包含 __prefix__）
    var result = [];
    for (var i = 0; i < selects.length; i++) {
      var select = selects[i];
      if (select.name && select.name.indexOf('__prefix__') === -1) {
        result.push(select);
      }
    }
    
    return result;
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
    console.log('[updateOptions] 开始更新选项，当事人数量:', parties.length);
    
    // 构建当事人 ID 到信息的映射
    var partyMap = {};
    parties.forEach(function(party) {
      partyMap[String(party.id)] = party;
    });
    
    var selects = getClientSelects();
    
    selects.forEach(function(select) {
      // 先保存当前选中的值（在清空选项之前）
      var currentValue = select.value;
      console.log('[updateOptions] 处理选择框:', select.name, '当前值:', currentValue);
      
      // 清空现有选项（保留空选项）
      while (select.options.length > 1) {
        select.remove(1);
      }
      
      // 添加新选项
      parties.forEach(function(party) {
        var opt = document.createElement('option');
        opt.value = String(party.id);
        // 显示来源标识
        var sourceLabel = party.source === 'contract' ? '[合同]' : '[补充协议]';
        opt.text = party.name + ' ' + sourceLabel;
        select.appendChild(opt);
      });
      
      // 恢复之前选中的值
      if (currentValue) {
        var party = partyMap[currentValue];
        if (party) {
          // 值在当事人列表中，直接设置
          select.value = currentValue;
          console.log('[updateOptions]   恢复选中值:', currentValue);
        } else {
          // 值不在当事人列表中，但我们仍然要保留它
          // 这种情况不应该发生（因为我们只填充合同当事人）
          // 但为了安全，我们添加一个临时选项
          console.log('[updateOptions]   值不在列表中，添加临时选项:', currentValue);
          var opt = document.createElement('option');
          opt.value = currentValue;
          opt.text = '当事人 #' + currentValue;
          select.appendChild(opt);
          select.value = currentValue;
        }
      }
    });
    
    console.log('[updateOptions] 更新完成');
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
   * 复制合同名称到案件名称
   * 当选择合同时，自动将合同名称填入案件名称字段
   */
  function copyContractNameToCaseName(contractSelect) {
    var caseNameInput = byId('id_name');
    if (!caseNameInput) return;
    
    // 获取选中的合同名称（从 option 的 text 中提取）
    var selectedOption = contractSelect.options[contractSelect.selectedIndex];
    if (!selectedOption || !selectedOption.value) {
      return;
    }
    
    var contractName = selectedOption.text;
    
    // 只在案件名称为空时自动填充，避免覆盖用户已输入的内容
    if (!caseNameInput.value || caseNameInput.value.trim() === '') {
      caseNameInput.value = contractName;
    }
  }

  /**
   * 自动填充合同当事人到案件当事人 inline
   * 
   * 简化逻辑：直接遍历现有选择框填充
   * 
   * @param {Array} parties - 当事人列表 [{id, name, source}, ...]
   */
  function autoFillCaseParties(parties) {
    console.log('[autoFill] 开始，原始当事人数量:', parties ? parties.length : 0);
    
    if (!parties || parties.length === 0) {
      console.log('[autoFill] 没有当事人，退出');
      return;
    }
    
    // 设置自动填充标志，防止 handleInlineAdded 干扰
    isAutoFilling = true;
    
    // ========== 步骤 1 & 2: 基于 client ID 去重 ==========
    var seenIds = {};
    var uniqueParties = [];
    for (var i = 0; i < parties.length; i++) {
      var party = parties[i];
      var idStr = String(party.id);
      if (!seenIds[idStr]) {
        seenIds[idStr] = true;
        uniqueParties.push(party);
      }
    }
    
    console.log('[autoFill] 步骤1&2: 去重后当事人数量:', uniqueParties.length);
    for (var i = 0; i < uniqueParties.length; i++) {
      console.log('[autoFill]   -', uniqueParties[i].name, '(ID:', uniqueParties[i].id, ')');
    }
    
    // ========== 步骤 3: 获取已存在的当事人，过滤出需要添加的 ==========
    var existingClientIds = {};
    var selects = getClientSelects();
    for (var i = 0; i < selects.length; i++) {
      if (selects[i].value) {
        existingClientIds[String(selects[i].value)] = true;
      }
    }
    
    var partiesToAdd = [];
    for (var i = 0; i < uniqueParties.length; i++) {
      var party = uniqueParties[i];
      if (!existingClientIds[String(party.id)]) {
        partiesToAdd.push(party);
      }
    }
    
    console.log('[autoFill] 步骤3: 需要添加的当事人数量:', partiesToAdd.length);
    
    if (partiesToAdd.length === 0) {
      console.log('[autoFill] 没有需要添加的当事人，退出');
      isAutoFilling = false;
      return;
    }
    
    // ========== 步骤 4: 查找添加按钮 ==========
    // 查找 CaseParty inline 的添加按钮（支持多种选择器）
    var addButton = document.querySelector(
      '.contract-party-inline .add-row a, ' +
      '.contract-party-inline a.add-row, ' +
      '#caseparty_set-group .add-row a, ' +
      '#caseparty_set-group a.add-row, ' +
      '[data-inline-type="tabular"] .add-row a'
    );
    
    if (!addButton) {
      // 尝试通过 client 选择框找到 inline 容器，再找添加按钮
      var firstSelect = getClientSelects()[0];
      if (firstSelect) {
        var inlineContainer = firstSelect.closest('.inline-group, .djn-group, fieldset');
        if (inlineContainer) {
          addButton = inlineContainer.querySelector('.add-row a, a.add-row');
        }
      }
    }
    
    if (!addButton) {
      console.error('[autoFill] 找不到添加按钮');
      isAutoFilling = false;
      return;
    }
    
    console.log('[autoFill] 找到添加按钮:', addButton);
    
    var currentIndex = 0;
    // 记录已填充的选择框（通过 name 属性）
    var filledSelectNames = {};
    
    /**
     * 填充一个选择框
     */
    function fillSelect(select, party) {
      var partyIdStr = String(party.id);
      
      // 检查选项是否存在
      var optionExists = false;
      for (var i = 0; i < select.options.length; i++) {
        if (select.options[i].value === partyIdStr) {
          optionExists = true;
          break;
        }
      }
      
      // 如果选项不存在，添加它
      if (!optionExists) {
        console.log('[autoFill]   选项不存在，添加新选项');
        var opt = document.createElement('option');
        opt.value = partyIdStr;
        var sourceLabel = party.source === 'contract' ? '[合同]' : '[补充协议]';
        opt.text = party.name + ' ' + sourceLabel;
        select.appendChild(opt);
      }
      
      // 设置选中值
      select.value = partyIdStr;
      filledSelectNames[select.name] = true;
      console.log('[autoFill]   已填充:', party.name, '(ID:', party.id, '), select.name:', select.name);
      return true;
    }
    
    /**
     * 查找一个空的选择框（未填充且值为空）
     */
    function findEmptySelect() {
      var allSelects = getClientSelects();
      for (var i = 0; i < allSelects.length; i++) {
        var select = allSelects[i];
        // 跳过已填充的
        if (filledSelectNames[select.name]) {
          continue;
        }
        // 检查是否为空
        if (!select.value || select.value === '') {
          return select;
        }
      }
      return null;
    }
    
    /**
     * 处理单个当事人
     */
    function processNextParty() {
      if (currentIndex >= partiesToAdd.length) {
        // 全部完成
        console.log('[autoFill] 步骤4: 全部当事人添加完成，共', currentIndex, '个');
        isAutoFilling = false;
        return;
      }
      
      var party = partiesToAdd[currentIndex];
      console.log('[autoFill] 步骤4: 处理第', currentIndex + 1, '/', partiesToAdd.length, '个当事人:', party.name);
      
      // 查找空的选择框
      var emptySelect = findEmptySelect();
      
      if (emptySelect) {
        // 有空选择框，直接填充
        console.log('[autoFill]   找到空选择框:', emptySelect.name);
        fillSelect(emptySelect, party);
        currentIndex++;
        setTimeout(processNextParty, 100);
      } else {
        // 没有空选择框，点击添加按钮创建新行
        var selectCountBefore = getClientSelects().length;
        console.log('[autoFill]   没有空选择框，创建新行，当前选择框数量:', selectCountBefore);
        addButton.click();
        
        // 等待新行创建
        setTimeout(function() {
          var selectCountAfter = getClientSelects().length;
          console.log('[autoFill]   点击后选择框数量:', selectCountAfter);
          
          if (selectCountAfter > selectCountBefore) {
            // 找到新创建的空选择框
            var newEmptySelect = findEmptySelect();
            if (newEmptySelect) {
              console.log('[autoFill]   新行已创建，选择框:', newEmptySelect.name);
              fillSelect(newEmptySelect, party);
              currentIndex++;
            } else {
              console.error('[autoFill]   创建新行后找不到空选择框');
              currentIndex++;
            }
          } else {
            console.error('[autoFill]   创建新行失败，选择框数量未增加');
            currentIndex++;
          }
          setTimeout(processNextParty, 100);
        }, 300);
      }
    }
    
    // 开始处理
    console.log('[autoFill] 步骤4: 开始逐个添加当事人...');
    processNextParty();
  }
  
  /**
   * 清空所有案件当事人
   * 点击每一行的删除按钮来删除当事人
   */
  function clearAllCaseParties() {
    console.log('[clearParties] 开始清空当事人...');
    
    // 使用更精确的选择器：查找 name 以 parties- 开头且以 -client 结尾的选择框
    // 这样可以确保只获取 CaseParty inline 的选择框
    var allSelects = document.querySelectorAll('select[name^="parties-"][name$="-client"]');
    
    // 过滤掉模板行
    var realSelects = [];
    for (var i = 0; i < allSelects.length; i++) {
      if (allSelects[i].name.indexOf('__prefix__') === -1) {
        realSelects.push(allSelects[i]);
      }
    }
    
    console.log('[clearParties] 当前当事人数量:', realSelects.length);
    
    // 收集所有需要删除的行
    var rowsToDelete = [];
    for (var i = 0; i < realSelects.length; i++) {
      var select = realSelects[i];
      // 只清空有值的行
      if (select.value) {
        var row = select.closest('tr, .dynamic-caseparty_set, .djn-item');
        if (row) {
          rowsToDelete.push({ row: row, selectName: select.name });
        }
      }
    }
    
    console.log('[clearParties] 需要删除的行数:', rowsToDelete.length);
    
    // 逐个删除（从后往前删除，避免索引问题）
    for (var i = rowsToDelete.length - 1; i >= 0; i--) {
      var item = rowsToDelete[i];
      var row = item.row;
      
      // 尝试找删除按钮（Django Admin / nested_admin 的删除按钮）
      var deleteBtn = row.querySelector('.inline-deletelink, .delete-handler, a.delete, .djn-remove-handler');
      if (deleteBtn) {
        console.log('[clearParties] 点击删除按钮:', item.selectName);
        deleteBtn.click();
      } else {
        // 如果没有删除按钮，尝试找删除复选框
        var deleteCheckbox = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
        if (deleteCheckbox) {
          console.log('[clearParties] 勾选删除复选框:', item.selectName);
          deleteCheckbox.checked = true;
          deleteCheckbox.dispatchEvent(new Event('change', { bubbles: true }));
        } else {
          // 最后尝试直接清空选择框的值
          var select = row.querySelector('select[name$="-client"]');
          if (select) {
            console.log('[clearParties] 直接清空选择框:', item.selectName);
            select.value = '';
          }
        }
      }
    }
    
    console.log('[clearParties] 清空完成');
  }
  
  /**
   * 处理合同字段变化
   * Requirements: 3.1, 3.2, 3.3
   */
  function handleContractChange() {
    var contractSelect = byId('id_contract');
    if (!contractSelect) return;
    
    var contractId = contractSelect.value;
    var previousContractId = contractSelect.dataset.previousValue;
    
    // 如果值没有变化，跳过处理（防止重复触发）
    if (contractId === previousContractId) {
      console.log('[handleContractChange] 合同值未变化，跳过');
      return;
    }
    
    console.log('[handleContractChange] 合同变化:', previousContractId, '->', contractId);
    
    // 复制合同名称到案件名称
    copyContractNameToCaseName(contractSelect);
    
    // 更新 inline 容器的过滤激活状态
    var inlineGroup = document.querySelector('.contract-party-inline, #caseparty_set-group');
    if (inlineGroup) {
      if (contractId) {
        inlineGroup.classList.add('contract-party-filter-active');
      } else {
        inlineGroup.classList.remove('contract-party-filter-active');
      }
    }
    
    // 如果切换了合同（从一个合同切换到另一个合同），先清空当事人
    var isContractChanged = previousContractId && contractId && contractId !== previousContractId;
    if (isContractChanged) {
      console.log('[handleContractChange] 合同已切换，清空当事人');
      clearAllCaseParties();
    }
    
    // 记录当前值，用于下次比较（在处理之前记录，防止重复触发）
    contractSelect.dataset.previousValue = contractId;
    
    if (contractId) {
      // 有合同，获取合同当事人并过滤
      // 如果是切换合同，需要等待清空完成后再填充
      if (isContractChanged) {
        setTimeout(function() {
          fetchContractPartiesAndFill(contractId, true);
        }, 500);
      } else {
        // 首次选择合同或初始化时
        var shouldAutoFill = !previousContractId;
        fetchContractPartiesAndFill(contractId, shouldAutoFill);
      }
    } else {
      // 无合同，恢复所有客户选项
      restoreAllClientOptions();
    }
  }
  
  /**
   * 获取合同当事人并可选自动填充
   * @param {string} contractId - 合同 ID
   * @param {boolean} shouldAutoFill - 是否自动填充当事人
   */
  function fetchContractPartiesAndFill(contractId, shouldAutoFill) {
    console.log('[fetch] 开始获取合同当事人, contractId:', contractId, 'shouldAutoFill:', shouldAutoFill);
    
    // 防止重复请求
    if (isLoading) {
      console.log('[fetch] 正在加载中，跳过');
      return;
    }
    
    // 检查缓存
    if (contractPartiesCache[contractId]) {
      console.log('[fetch] 使用缓存数据，当事人数量:', contractPartiesCache[contractId].length);
      // 如果需要自动填充，先填充再更新选项（避免选项被过滤导致填充失败）
      if (shouldAutoFill) {
        autoFillCaseParties(contractPartiesCache[contractId]);
        // 填充完成后再更新选项（延迟执行，等待 isAutoFilling 重置）
        setTimeout(function() {
          updateClientOptions(contractPartiesCache[contractId]);
        }, 5000);
      } else {
        updateClientOptions(contractPartiesCache[contractId]);
      }
      return;
    }
    
    setLoadingState(true);
    console.log('[fetch] 发起 API 请求...');
    
    var url = '/api/v1/contracts/contracts/' + contractId + '/all-parties';
    
    fetch(url)
      .then(function(response) {
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }
        return response.json();
      })
      .then(function(parties) {
        console.log('[fetch] API 返回数据，当事人数量:', parties.length);
        for (var i = 0; i < parties.length; i++) {
          console.log('[fetch]   -', parties[i].name, '(ID:', parties[i].id, ', source:', parties[i].source, ')');
        }
        
        // 缓存结果
        contractPartiesCache[contractId] = parties;
        
        // 如果需要自动填充，先填充再更新选项
        if (shouldAutoFill) {
          console.log('[fetch] 开始自动填充...');
          autoFillCaseParties(parties);
          // 填充完成后再更新选项（增加延迟时间）
          setTimeout(function() {
            console.log('[fetch] 延迟更新选项...');
            updateClientOptions(parties);
          }, 5000);
        } else {
          updateClientOptions(parties);
        }
      })
      .catch(function(error) {
        console.error('[fetch] 获取合同当事人失败:', error);
        // 出错时恢复所有选项
        restoreAllClientOptions();
      })
      .finally(function() {
        setLoadingState(false);
      });
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
    // 如果正在自动填充，跳过选项更新，避免干扰
    if (isAutoFilling) {
      console.log('[handleInlineAdded] 自动填充进行中，跳过');
      return;
    }
    
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
