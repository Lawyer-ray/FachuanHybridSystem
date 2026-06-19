/**
 * admin_case_form.js
 * 案件 Admin 表单 - 初始化入口
 *
 * 负责：
 * 1. 案件类型字段的显示/隐藏逻辑
 * 2. 在 DOMContentLoaded 时初始化合同当事人过滤
 * 3. 监听 inline 行添加事件，同步过滤状态
 *
 * 依赖（按顺序加载）:
 *   1. admin_case_form_utils.js   -- 工具函数
 *   2. admin_case_form_contract.js -- 合同当事人过滤
 */
;(function(){
  'use strict';

  var ns = window.AdminCaseForm;
  var byId    = ns.byId;
  var fieldDivs = ns.fieldDivs;
  var inputsByNameSuffix = ns.inputsByNameSuffix;

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
    // 不再自动清空 current_stage，避免页面初始化时抹掉已保存值
    // （例如 case_type=execution 且 current_stage=enforcement 的场景）
    void show
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
    ns.initContractPartyFilter();

    // 监听 inline 行添加事件（兼容 Django Admin / nested_admin）
    // 使用 debounce 替代多层 setTimeout，避免重复触发导致 select 选项闪烁
    var _inlineAddedTimer = null;
    document.body.addEventListener('formset:added', function() {
      clearTimeout(_inlineAddedTimer);
      _inlineAddedTimer = setTimeout(ns.handleInlineAdded, 150);
    });

    // 兜底：监听"添加另一个案件当事人"点击，确保新行总会触发过滤
    var _clickAddTimer = null;
    document.body.addEventListener('click', function(e) {
      var target = e.target;
      if (!target || typeof target.closest !== 'function') {
        return;
      }
      var addLink = target.closest(
        '.contract-party-inline .add-row a, .contract-party-inline a.add-row, #caseparty_set-group .add-row a, #caseparty_set-group a.add-row'
      );
      if (!addLink) {
        return;
      }

      clearTimeout(_clickAddTimer);
      _clickAddTimer = setTimeout(ns.handleInlineAdded, 150);
    });
  });

})();
