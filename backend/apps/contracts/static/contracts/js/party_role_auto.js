/**
 * 当事人身份自动填充：选择非我方当事人时，自动将身份设为"对方当事人"
 */
(function () {
  "use strict";

  const OPPOSING_VALUE = "OPPOSING";

  function handleClientChange(clientSelect) {
    const clientId = clientSelect.value;
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
    select.addEventListener("change", function () {
      handleClientChange(this);
    });
  }

  function bindAll() {
    document.querySelectorAll('select[name*="-client"]').forEach(function (sel) {
      // 只处理当事人 inline 中的 client（同行有 role select）
      const row = sel.closest("tr");
      if (row && row.querySelector('select[name*="-role"]')) {
        bindClientSelect(sel);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindAll();
    // 监听动态新增行
    const observer = new MutationObserver(bindAll);
    observer.observe(document.body, { childList: true, subtree: true });
  });
})();
