/**
 * 当事人身份自动填充：选择非我方当事人时，自动将身份设为"对方当事人"
 * 适用于 ContractPartyInline 和 SupplementaryAgreementPartyInline
 */
(function () {
  "use strict";

  const OPPOSING_VALUE = "OPPOSING";

  // Django admin inline 行的 CSS class 前缀（dynamic-{prefix}）
  // ContractParty: contract_parties；SupplementaryAgreementParty: parties
  const ROW_SELECTORS = [
    ".dynamic-contract_parties",
    ".dynamic-parties",
    ".dynamic-contractparty_set",
    ".dynamic-supplementaryagreementparty_set",
  ].join(", ");

  function isPartyRow(el) {
    return (
      el.querySelector('select[id*="-role"]') !== null ||
      el.querySelector('select[name*="-role"]') !== null
    );
  }

  function bindRow(row) {
    if (!isPartyRow(row)) return;

    // autocomplete 场景：Django select2 autocomplete 会有隐藏 input 存 id
    // 普通 select 场景：直接监听 select change
    const clientSelect = row.querySelector('select[id*="-client"]');

    if (clientSelect) {
      clientSelect.addEventListener("change", function () {
        handleClientChange(row, this.value);
      });
    }

    // autocomplete 隐藏 input（name 含 "-client"，type=hidden 或无 type）
    const hiddenInputs = row.querySelectorAll('input[name*="-client"]');
    hiddenInputs.forEach(function (input) {
      if (input.type === "hidden" || input.type === "") {
        // MutationObserver 监听 value attribute 变化（select2 通过 JS 设置）
        const obs = new MutationObserver(function () {
          if (input.value) handleClientChange(row, input.value);
        });
        obs.observe(input, { attributes: true, attributeFilter: ["value"] });
        input.addEventListener("change", function () {
          if (this.value) handleClientChange(row, this.value);
        });
      }
    });
  }

  function handleClientChange(row, clientId) {
    if (!clientId) return;
    fetch("/api/v1/clients/" + clientId, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.ok ? res.json() : null;
      })
      .then(function (data) {
        if (!data) return;
        if (data.is_our_client === false) {
          const roleSelect = row.querySelector('select[id*="-role"], select[name*="-role"]');
          if (roleSelect) roleSelect.value = OPPOSING_VALUE;
        }
      })
      .catch(function () {});
  }

  function initAll() {
    document.querySelectorAll(ROW_SELECTORS).forEach(bindRow);

    const observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          if (node.nodeType !== 1) return;
          if (node.matches && node.matches(ROW_SELECTORS)) {
            bindRow(node);
          } else if (node.querySelectorAll) {
            node.querySelectorAll(ROW_SELECTORS).forEach(bindRow);
          }
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  document.addEventListener("DOMContentLoaded", initAll);
})();
