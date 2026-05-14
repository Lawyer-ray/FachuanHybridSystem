/**
 * Contract and supplementary-agreement party helpers:
 * 1. Auto-set role to OPPOSING for non-our-clients.
 * 2. Add fill buttons for supplementary agreement party groups.
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
      .then(function (res) {
        return res.ok ? res.json() : null;
      })
      .then(function (data) {
        if (data && (data.is_our_client === false || data.is_our_client === null)) {
          roleSelect.value = OPPOSING_VALUE;
        }
      })
      .catch(function () {});
  }

  function bindClientSelect(select) {
    const $ = window.django && window.django.jQuery;

    if (!select.dataset.partyRoleBound) {
      select.dataset.partyRoleBound = "1";
      select.addEventListener("change", function () {
        checkAndSetRole(this, this.value);
      });
    }

    if ($ && select.classList.contains("admin-autocomplete")) {
      $(select).off("select2:select.partyRole");
      $(select).on("select2:select.partyRole", function (e) {
        const id = e.params && e.params.data && e.params.data.id;
        checkAndSetRole(select, id || select.value);
      });
    }
  }

  function bindAllClientSelects(root) {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll('select[name*="-client"]').forEach(function (sel) {
      if (sel.name.includes("__prefix__")) return;
      const row = sel.closest("tr");
      if (row && row.querySelector('select[name*="-role"]')) {
        bindClientSelect(sel);
      }
    });
  }

  function getSourceParties(suppIndex) {
    const parties = [];
    const $ = window.django && window.django.jQuery;

    if (suppIndex === 0) {
      document.querySelectorAll('select[name^="contract_parties-"][name$="-client"]').forEach(function (sel) {
        if (sel.name.includes("__prefix__") || !sel.value) return;
        const row = sel.closest("tr");
        const roleSelect = row && row.querySelector('select[name*="-role"]');
        const selectedOption = sel.options[sel.selectedIndex];
        parties.push({
          id: sel.value,
          text: selectedOption ? selectedOption.text : sel.value,
          role: roleSelect ? roleSelect.value : "PRINCIPAL",
        });
      });
    } else {
      const prevIndex = suppIndex - 1;
      const prefix = "supplementary_agreements-" + prevIndex + "-parties-";
      document.querySelectorAll('select[name^="' + prefix + '"][name$="-client"]').forEach(function (sel) {
        if (sel.name.includes("__prefix__") || !sel.value) return;
        const row = sel.closest("tr");
        const roleSelect = row && row.querySelector('select[name*="-role"]');
        let text = sel.value;
        if ($ && sel.classList.contains("admin-autocomplete")) {
          const data = $(sel).select2("data");
          if (data && data[0]) text = data[0].text;
        } else {
          const opt = sel.options[sel.selectedIndex];
          if (opt) text = opt.text;
        }
        parties.push({
          id: sel.value,
          text: text,
          role: roleSelect ? roleSelect.value : "PRINCIPAL",
        });
      });
    }

    return parties;
  }

  function fillParties(groupId, parties) {
    if (!parties.length) return;
    const $ = window.django && window.django.jQuery;
    const group = document.getElementById(groupId);
    if (!group) return;

    const prefix = groupId.replace("-group", "");
    const addBtn = group.querySelector(".djn-add-item a");
    if (!addBtn) return;

    function getExistingRows() {
      return Array.from(
        group.querySelectorAll('select[name^="' + prefix + '-"][name$="-client"]:not([name*="__prefix__"])')
      );
    }

    const needed = parties.length;
    const current = getExistingRows().length;

    function doFill() {
      const rows = getExistingRows();
      parties.forEach(function (party, i) {
        const sel = rows[i];
        if (!sel) return;
        const row = sel.closest("tr");
        const roleSelect = row && row.querySelector('select[name*="-role"]');

        if ($ && sel.classList.contains("admin-autocomplete")) {
          const option = new Option(party.text, party.id, true, true);
          $(sel).append(option).trigger("change");
        } else {
          sel.value = party.id;
        }

        if (roleSelect) roleSelect.value = party.role;
      });
    }

    function addRowsAndFill(remaining) {
      if (remaining <= 0) {
        doFill();
        return;
      }
      addBtn.click();
      setTimeout(function () {
        addRowsAndFill(remaining - 1);
      }, 50);
    }

    addRowsAndFill(Math.max(0, needed - current));
  }

  function insertFillButton(group) {
    if (group.dataset.fillBtnAdded) return;
    group.dataset.fillBtnAdded = "1";

    const match = group.id.match(/supplementary_agreements-(\d+)-parties-group/);
    if (!match) return;
    const suppIndex = parseInt(match[1], 10);

    const i18n = window.CONTRACTS_I18N || {};
    const label =
      suppIndex === 0
        ? i18n.fillContractParties || "填充合同当事人"
        : i18n.fillPrevSuppParties || "填充上一份补充协议当事人";

    const btn = document.createElement("a");
    btn.href = "javascript://";
    btn.textContent = label;
    btn.style.cssText = "margin-left:12px;color:#417690;cursor:pointer;font-size:13px;";
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const parties = getSourceParties(suppIndex);
      if (!parties.length) {
        alert(suppIndex === 0 ? "合同当事人为空" : "上一份补充协议当事人为空");
        return;
      }
      fillParties(group.id, parties);
    });

    const addItem = group.querySelector(".djn-add-item");
    if (addItem) addItem.appendChild(btn);
  }

  function bindAllFillButtons(root) {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll('[id*="supplementary_agreements-"][id$="-parties-group"]').forEach(function (group) {
      if (group.id.includes("-empty-")) return;
      insertFillButton(group);
    });
  }

  function bindFromNode(node) {
    if (!(node instanceof Element)) return;

    if (node.matches('select[name*="-client"]')) {
      const row = node.closest("tr");
      if (row && row.querySelector('select[name*="-role"]')) {
        bindClientSelect(node);
      }
    }

    if (node.id && node.id.match(/supplementary_agreements-\d+-parties-group/) && !node.id.includes("-empty-")) {
      insertFillButton(node);
    }

    bindAllClientSelects(node);
    bindAllFillButtons(node);
  }

  function getObserverRoots() {
    const roots = [];
    const seen = new Set();

    [
      document.getElementById("contract_parties-group"),
      document.getElementById("contractparty_set-group"),
      document.getElementById("supplementary_agreements-group"),
    ].forEach(function (root) {
      if (!root || seen.has(root)) return;
      seen.add(root);
      roots.push(root);
    });

    document.querySelectorAll('[id*="supplementary_agreements-"][id$="-parties-group"]').forEach(function (root) {
      if (!root || root.id.includes("-empty-") || seen.has(root)) return;
      seen.add(root);
      roots.push(root);
    });

    return roots;
  }

  function observeRoot(root) {
    if (!root || root.dataset.partyRoleObserverBound === "1") return;
    root.dataset.partyRoleObserverBound = "1";

    const observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          bindFromNode(node);
        });
      });
    });

    observer.observe(root, { childList: true, subtree: true });
  }

  function init() {
    bindAllClientSelects();
    bindAllFillButtons();
    getObserverRoots().forEach(function (root) {
      observeRoot(root);
    });
  }

  (function () {
    const style = document.createElement("style");
    style.textContent =
      "#contract_parties-group td.original p," +
      "#assignments-group td.original p," +
      "#supplementary_agreements-group td.original p { display:none; }";
    document.head.appendChild(style);
  })();

  document.addEventListener("change", function (e) {
    const target = e.target;
    const id = (target.id || "") + " " + (target.name || "");
    if (
      id.match(/contract_parties.*client/) ||
      id.match(/contract_parties.*role/) ||
      id.match(/contractparty_set.*client/) ||
      id.match(/contractparty_set.*role/)
    ) {
      const btn = document.querySelector(".auto-contract-name-btn");
      if (!btn) return;
      setTimeout(function () {
        btn.dispatchEvent(new CustomEvent("auto-contract-name-refresh", { bubbles: false }));
      }, 150);
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    init();
  });
})();
