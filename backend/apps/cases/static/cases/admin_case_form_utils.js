/**
 * admin_case_form_utils.js
 * 案件 Admin 表单 - 工具函数
 *
 * 提供 DOM 查询、Select2 刷新等共用工具函数，
 * 供 admin_case_form_contract.js 和 admin_case_form.js 使用。
 */
;(function(global){
  'use strict';

  // ============================================================
  // 工具函数
  // ============================================================
  function byId(id){ return document.getElementById(id); }

  function fieldDivs(name){
    return document.querySelectorAll('div.field-' + name);
  }

  function selectsByNameSuffix(suffix){
    return document.querySelectorAll('select[name$="' + suffix + '"]');
  }

  function inputsByNameSuffix(suffix){
    return document.querySelectorAll('input[name$="' + suffix + '"]');
  }

  /**
   * 销毁并重建 Select2 实例，使其重新读取 <select> 的 option 并刷新显示。
   * 用于在直接操作 DOM 修改 option 后同步 Select2 的内部状态。
   * 注意：Django admin 将 jQuery 放在 django.jQuery 命名空间（noConflict）。
   */
  function refreshSelect2(el) {
    var jq = window.django && window.django.jQuery;
    if (!jq || typeof jq.fn.select2 === 'undefined') return;
    try { jq(el).select2('destroy'); } catch (_e) { /* 尚未初始化 */ }
    jq(el).select2();
  }

  // ============================================================
  // 暴露到全局命名空间
  // ============================================================
  global.AdminCaseForm = global.AdminCaseForm || {};
  var ns = global.AdminCaseForm;

  ns.byId              = byId;
  ns.fieldDivs         = fieldDivs;
  ns.selectsByNameSuffix = selectsByNameSuffix;
  ns.inputsByNameSuffix  = inputsByNameSuffix;
  ns.refreshSelect2    = refreshSelect2;

})(window);
