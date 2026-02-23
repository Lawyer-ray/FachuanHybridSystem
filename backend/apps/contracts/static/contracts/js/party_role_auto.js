/**
 * 当事人身份自动填充：选择非我方当事人时，自动将身份设为"对方当事人"
 * 支持普通 select 和 select2 autocomplete 两种场景
 */
(function () {
  "use strict";

  const OPPOSING_VALUE = "OPPOSING";

  function checkAndSetRole(clientSelect, clientId) {
    if (!clientId) return;
    const row = clientSelect.closest("tr");
    if (!row) return;
    const roleSelect = row.querySelector('select[name*="-role"]');
    if (!roleSelect) return;

    fetch("/api/v1/client/clients/" + clientId, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        if (data && data.is_our_client === false) {
          roleSelect.value = OPPOSING_VALUE;
        }
      })
      .catch(function () {});
  }

  function bindClientSelect(select) {
    if (select.dataset.partyRoleBound) return;
    select.dataset.partyRoleBound = "1";

    // 普通 select
    select.addEventListener("change", function () {
      checkAndSetRole(this, this.value);
    });

    // select2 autocomplete：从事件 params 取 id，避免时序问题
    const $ = window.django && window.django.jQuery;
    if ($ && select.classList.contains("admin-autocomplete")) {
      $(select).on("select2:select", function (e) {
        const id = e.params && e.params.data && e.params.data.id;
        checkAndSetRole(select, id || select.value);
      });
    }
  }

  function bindAll() {
    document.querySelectorAll('select[name*="-client"]').forEach(function (sel) {
      if (sel.dataset.partyRoleBound) return;
      const row = sel.closest("tr");
      if (row && row.querySelector('select[name*="-role"]')) {
        bindClientSelect(sel);
      }
    });
  }

  function init() {
    bindAll();
    const observer = new MutationObserver(bindAll);
    observer.observe(document.body, { childList: true, subtree: true });
  }

  document.addEventListener("DOMContentLoaded", function () {
    init();
    setTimeout(bindAll, 300);
  });
})();
