/**
 * 合同/补充协议当事人辅助功能：
 * 1. 选择非我方当事人时，自动将身份设为"对方当事人"
 * 2. 新增补充协议时，提供"填充合同当事人"或"填充上一份补充协议当事人"按钮
 */
(function () {
  "use strict";

  const OPPOSING_VALUE = "OPPOSING";

  // ─── 功能一：自动设置身份 ───────────────────────────────────────────

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
        if (data) {
          // 非我方当事人（is_our_client 为 false 或 null）自动设为对方当事人
          if (data.is_our_client === false || data.is_our_client === null) {
            roleSelect.value = OPPOSING_VALUE;
          }
        }
      })
      .catch(function () {});
  }

  function bindClientSelect(select) {
    const $ = window.django && window.django.jQuery;
    
    // 普通 change 事件（只绑定一次）
    if (!select.dataset.partyRoleBound) {
      select.dataset.partyRoleBound = "1";
      select.addEventListener("change", function () {
        checkAndSetRole(this, this.value);
      });
    }

    // select2 事件（每次都重新绑定，因为 select2 可能被重新初始化）
    if ($ && select.classList.contains("admin-autocomplete")) {
      // 先解绑旧事件，避免重复绑定
      $(select).off("select2:select.partyRole");
      // 重新绑定，使用命名空间避免冲突
      $(select).on("select2:select.partyRole", function (e) {
        const id = e.params && e.params.data && e.params.data.id;
        checkAndSetRole(select, id || select.value);
      });
    }
  }

  function bindAllClientSelects() {
    document.querySelectorAll('select[name*="-client"]').forEach(function (sel) {
      // 跳过模板行
      if (sel.name.includes("__prefix__")) return;
      const row = sel.closest("tr");
      if (row && row.querySelector('select[name*="-role"]')) {
        bindClientSelect(sel);
      }
    });
  }

  // ─── 功能二：填充当事人按钮 ─────────────────────────────────────────

  /**
   * 读取来源当事人列表
   * @param {number} suppIndex - 当前补充协议的 index（0=第一个）
   * @returns {Array<{id: string, text: string, role: string}>}
   */
  function getSourceParties(suppIndex) {
    const parties = [];
    const $ = window.django && window.django.jQuery;

    if (suppIndex === 0) {
      // 从合同当事人读取（普通 select，有完整 option text）
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
      // 从上一份补充协议当事人读取（select2，用 select2('data') 取 text）
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

  /**
   * 向目标 parties-group 填充当事人
   * @param {string} groupId - 如 "supplementary_agreements-1-parties-group"
   * @param {Array} parties
   */
  function fillParties(groupId, parties) {
    if (!parties.length) return;
    const $ = window.django && window.django.jQuery;
    const group = document.getElementById(groupId);
    if (!group) return;

    // 解析 prefix，如 "supplementary_agreements-1-parties"
    const prefix = groupId.replace("-group", "");

    // 获取当前已有的空行（TOTAL_FORMS - INITIAL_FORMS 个）
    // 需要点击"添加"按钮来创建足够的行
    const addBtn = group.querySelector(".djn-add-item a");
    if (!addBtn) return;

    // 当前已有的行（非 empty-form、非 __prefix__）
    function getExistingRows() {
      return Array.from(
        group.querySelectorAll('select[name^="' + prefix + '-"][name$="-client"]:not([name*="__prefix__"])')
      );
    }

    const existingRows = getExistingRows();
    // 需要的行数
    const needed = parties.length;
    // 已有行数（包括空行）
    let current = existingRows.length;

    // 点击添加按钮补足行数
    function addRowsAndFill(remaining) {
      if (remaining <= 0) {
        doFill();
        return;
      }
      addBtn.click();
      // 等 nested_admin 渲染新行
      setTimeout(function () {
        addRowsAndFill(remaining - 1);
      }, 50);
    }

    function doFill() {
      const rows = getExistingRows();
      parties.forEach(function (party, i) {
        const sel = rows[i];
        if (!sel) return;
        const row = sel.closest("tr");
        const roleSelect = row && row.querySelector('select[name*="-role"]');

        // 设置 select2 值
        if ($ && sel.classList.contains("admin-autocomplete")) {
          const option = new Option(party.text, party.id, true, true);
          $(sel).append(option).trigger("change");
        } else {
          sel.value = party.id;
        }

        // 设置 role
        if (roleSelect) roleSelect.value = party.role;
      });
    }

    addRowsAndFill(Math.max(0, needed - current));
  }

  /**
   * 在 parties-group 的 add-item 旁插入填充按钮
   * @param {HTMLElement} group
   */
  function insertFillButton(group) {
    if (group.dataset.fillBtnAdded) return;
    group.dataset.fillBtnAdded = "1";

    // 解析 index：supplementary_agreements-N-parties-group
    const match = group.id.match(/supplementary_agreements-(\d+)-parties-group/);
    if (!match) return;
    const suppIndex = parseInt(match[1], 10);

    const label = suppIndex === 0 ? "填充合同当事人" : "填充上一份补充协议当事人";

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

  function bindAllFillButtons() {
    document.querySelectorAll('[id*="supplementary_agreements-"][id$="-parties-group"]').forEach(function (group) {
      // 排除 empty template
      if (group.id.includes("-empty-")) return;
      insertFillButton(group);
    });
  }

  // ─── 初始化 ──────────────────────────────────────────────────────────

  function init() {
    bindAllClientSelects();
    bindAllFillButtons();

    const observer = new MutationObserver(function () {
      bindAllClientSelects();
      bindAllFillButtons();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  // 隐藏 inline 行里的 __str__ 显示文字（td.original > p）
  (function () {
    const style = document.createElement("style");
    style.textContent =
      "#contract_parties-group td.original p," +
      "#assignments-group td.original p," +
      "#supplementary_agreements-group td.original p { display:none; }";
    document.head.appendChild(style);
  })();

  document.addEventListener("DOMContentLoaded", function () {
    init();
    setTimeout(function () {
      bindAllClientSelects();
      bindAllFillButtons();
    }, 300);
  });
})();
