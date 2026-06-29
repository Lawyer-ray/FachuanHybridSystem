/**
 * 合同/补充协议当事人辅助功能：
 * 1. 选择非我方当事人时，自动将身份设为"对方当事人"
 * 2. 新增补充协议时，提供"填充合同当事人"或"填充上一份补充协议当事人"按钮
 */
(function () {
  "use strict";

  const OPPOSING_VALUE = "OPPOSING";

  // ─── 功能一：自动设置身份 ───────────────────────────────────────────

  // 记录正在进行的请求，支持取消和提交守卫
  var pendingRequests = new Map();

  function checkAndSetRole(clientSelect, clientId) {
    if (!clientId) return;
    // 找到同行或同 group 内的 role select
    var roleSelect = findRoleSelect(clientSelect);
    if (!roleSelect) return;

    // 取消该行之前的请求
    var key = clientSelect.name;
    if (pendingRequests.has(key)) {
      pendingRequests.get(key).abort();
    }

    var controller = new AbortController();
    pendingRequests.set(key, controller);

    fetch("/api/v1/client/clients/" + clientId, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
      signal: controller.signal,
    })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        pendingRequests.delete(key);
        if (data) {
          // 非我方当事人（is_our_client 为 false 或 null）自动设为对方当事人
          if (data.is_our_client === false || data.is_our_client === null) {
            roleSelect.value = OPPOSING_VALUE;
          }
        }
      })
      .catch(function () { pendingRequests.delete(key); });
  }

  /**
   * 从 client select 出发，找到对应的 role select。
   * 优先在同一个 <tr> 内查找，找不到则向上找 group 容器。
   */
  function findRoleSelect(clientSelect) {
    var row = clientSelect.closest("tr");
    if (row) {
      var sel = row.querySelector('select[name*="-role"]');
      if (sel) return sel;
    }
    // fallback：向上找 group 容器
    var group = clientSelect.closest(".dynamic-contract_parties, .dynamic-supplementary_agreements_parties, [id*='parties-group']");
    if (group) {
      return group.querySelector('select[name*="-role"]');
    }
    return null;
  }

  function bindClientSelect(select) {
    var $ = window.django && window.django.jQuery;

    // 普通 change 事件（只绑定一次）
    if (!select.dataset.partyRoleBound) {
      select.dataset.partyRoleBound = "1";
      select.addEventListener("change", function () {
        checkAndSetRole(this, this.value);
      });
    }

    // select2 事件（每次都重新绑定，因为 select2 可能被重新初始化）
    if ($ && select.classList.contains("admin-autocomplete")) {
      $(select).off("select2:select.partyRole");
      $(select).on("select2:select.partyRole", function (e) {
        var id = e.params && e.params.data && e.params.data.id;
        checkAndSetRole(select, id || select.value);
      });
    }
  }

  function bindAllClientSelects() {
    document.querySelectorAll('select[name*="-client"]').forEach(function (sel) {
      if (sel.name.includes("__prefix__")) return;
      var row = sel.closest("tr");
      if (row && row.querySelector('select[name*="-role"]')) {
        bindClientSelect(sel);
      }
    });
  }

  // ─── 补充机制：当 role select 被插入 DOM 时，检查 client 是否已选 ──

  function checkExistingClientOnRoleInsert(addedNode) {
    if (!addedNode.querySelectorAll) return;
    // 检查新增节点内的 role select
    var roleSelects = addedNode.querySelectorAll('select[name*="-role"]');
    roleSelects.forEach(function (roleSelect) {
      if (roleSelect.name.includes("__prefix__")) return;
      var row = roleSelect.closest("tr");
      if (!row) return;
      var clientSelect = row.querySelector('select[name*="-client"]');
      if (clientSelect && !clientSelect.name.includes("__prefix__") && clientSelect.value) {
        // client 已选但 role 还是默认值，触发一次检查
        if (roleSelect.value === "PRINCIPAL") {
          checkAndSetRole(clientSelect, clientSelect.value);
        }
      }
    });
  }

  // ─── 提交守卫：确保 AJAX 完成后再提交 ──────────────────────────────

  function setupSubmitGuard() {
    document.addEventListener("submit", function (e) {
      if (pendingRequests.size === 0) return;
      e.preventDefault();
      // 等待所有请求完成后再提交
      var form = e.target;
      var promises = Array.from(pendingRequests.values()).map(function (ctrl) {
        return new Promise(function (resolve) {
          // 请求会在 abort 或完成后 resolve
          var check = setInterval(function () {
            if (!pendingRequests.has(ctrl)) { clearInterval(check); resolve(); }
          }, 50);
          setTimeout(function () { clearInterval(check); resolve(); }, 3000);
        });
      });
      Promise.all(promises).then(function () { form.submit(); });
    }, true);
  }

  // ─── 功能二：填充当事人按钮 ─────────────────────────────────────────

  function getSourceParties(suppIndex) {
    var parties = [];
    var $ = window.django && window.django.jQuery;

    if (suppIndex === 0) {
      document.querySelectorAll('select[name^="contract_parties-"][name$="-client"]').forEach(function (sel) {
        if (sel.name.includes("__prefix__") || !sel.value) return;
        var row = sel.closest("tr");
        var roleSelect = row && row.querySelector('select[name*="-role"]');
        var selectedOption = sel.options[sel.selectedIndex];
        parties.push({
          id: sel.value,
          text: selectedOption ? selectedOption.text : sel.value,
          role: roleSelect ? roleSelect.value : "PRINCIPAL",
        });
      });
    } else {
      var prevIndex = suppIndex - 1;
      var prefix = "supplementary_agreements-" + prevIndex + "-parties-";
      document.querySelectorAll('select[name^="' + prefix + '"][name$="-client"]').forEach(function (sel) {
        if (sel.name.includes("__prefix__") || !sel.value) return;
        var row = sel.closest("tr");
        var roleSelect = row && row.querySelector('select[name*="-role"]');
        var text = sel.value;
        if ($ && sel.classList.contains("admin-autocomplete")) {
          var data = $(sel).select2("data");
          if (data && data[0]) text = data[0].text;
        } else {
          var opt = sel.options[sel.selectedIndex];
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
    var $ = window.django && window.django.jQuery;
    var group = document.getElementById(groupId);
    if (!group) return;

    var prefix = groupId.replace("-group", "");
    var addBtn = group.querySelector(".djn-add-item a");
    if (!addBtn) return;

    function getExistingRows() {
      return Array.from(
        group.querySelectorAll('select[name^="' + prefix + '-"][name$="-client"]:not([name*="__prefix__"])')
      );
    }

    var needed = parties.length;
    var current = getExistingRows().length;

    function addRowsAndFill(remaining) {
      if (remaining <= 0) { doFill(); return; }
      addBtn.click();
      setTimeout(function () { addRowsAndFill(remaining - 1); }, 50);
    }

    function doFill() {
      var rows = getExistingRows();
      parties.forEach(function (party, i) {
        var sel = rows[i];
        if (!sel) return;
        var row = sel.closest("tr");
        var roleSelect = row && row.querySelector('select[name*="-role"]');

        if ($ && sel.classList.contains("admin-autocomplete")) {
          var option = new Option(party.text, party.id, true, true);
          $(sel).append(option).trigger("change");
        } else {
          sel.value = party.id;
        }

        if (roleSelect) roleSelect.value = party.role;
      });
    }

    addRowsAndFill(Math.max(0, needed - current));
  }

  function insertFillButton(group) {
    if (group.dataset.fillBtnAdded) return;
    group.dataset.fillBtnAdded = "1";

    var match = group.id.match(/supplementary_agreements-(\d+)-parties-group/);
    if (!match) return;
    var suppIndex = parseInt(match[1], 10);

    var i18n = window.CONTRACTS_I18N || {};
    var label = suppIndex === 0
      ? (i18n.fillContractParties || "填充合同当事人")
      : (i18n.fillPrevSuppParties || "填充上一份补充协议当事人");

    var btn = document.createElement("a");
    btn.href = "javascript://";
    btn.textContent = label;
    btn.style.cssText = "margin-left:12px;color:var(--fc-admin-blue);cursor:pointer;font-size:13px;";
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      var parties = getSourceParties(suppIndex);
      if (!parties.length) {
        alert(suppIndex === 0 ? "合同当事人为空" : "上一份补充协议当事人为空");
        return;
      }
      fillParties(group.id, parties);
    });

    var addItem = group.querySelector(".djn-add-item");
    if (addItem) addItem.appendChild(btn);
  }

  function bindAllFillButtons() {
    document.querySelectorAll('[id*="supplementary_agreements-"][id$="-parties-group"]').forEach(function (group) {
      if (group.id.includes("-empty-")) return;
      insertFillButton(group);
    });
  }

  // ─── 初始化 ──────────────────────────────────────────────────────────

  function init() {
    bindAllClientSelects();
    bindAllFillButtons();
    setupSubmitGuard();

    // 监听 DOM 变化：新行插入时重新绑定 + 检查已选 client
    var observer = new MutationObserver(function (mutations) {
      bindAllClientSelects();
      bindAllFillButtons();
      mutations.forEach(function (m) {
        m.addedNodes.forEach(function (node) {
          checkExistingClientOnRoleInsert(node);
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });

    // document 级 select2 事件委托（兜底：即使 bindClientSelect 没绑定到也能捕获）
    var $ = window.django && window.django.jQuery;
    if ($) {
      $(document).on("select2:select.partyRoleDelegation", 'select[name*="-client"]', function (e) {
        var id = e.params && e.params.data && e.params.data.id;
        checkAndSetRole(this, id || this.value);
      });
    }
  }

  // 隐藏 inline 行里的 __str__ 显示文字
  (function () {
    var style = document.createElement("style");
    style.textContent =
      "#contract_parties-group td.original p," +
      "#assignments-group td.original p," +
      "#supplementary_agreements-group td.original p { display:none; }";
    document.head.appendChild(style);
  })();

  document.addEventListener("DOMContentLoaded", function () {
    init();
    // 延迟再绑定一次，确保 nested_admin 渲染完成
    setTimeout(function () {
      bindAllClientSelects();
      bindAllFillButtons();
    }, 300);
  });
})();
