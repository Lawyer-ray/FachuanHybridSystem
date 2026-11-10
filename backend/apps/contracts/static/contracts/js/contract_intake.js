/**
 * 新建合同页：拖拽导入合同 → LLM 自动解析 → 回填表单。
 *
 * 设计约束（都是踩过的坑，改之前先读）：
 *
 * 1. **当事人 / 律师是 select2 autocomplete**（`autocomplete_fields`），不是普通
 *    `<select>`。直接 `input.value = id` 只会改 DOM 属性，select2 内部状态不同步，
 *    提交时 Django 收不到值 → 静默存成空。必须走 select2 的 `data` API：
 *    先按名称向后端 autocomplete 接口查到 `{id, text}`，再 `$(el).select2({data:[...]})`。
 * 2. **动态加行必须触发 `formset:added`**，否则新行里的 `.admin-autocomplete`
 *    不会被初始化成 select2（Django admin 的 autocomplete.js 只监听这个事件）。
 * 3. **只回填、不提交**。用户复核后自己点「保存」，避免 AI 结果直接落库。
 */
(function () {
  "use strict";

  var ENDPOINT_OPTIONS = "/admin/contracts/contract/auto-intake/options/";
  var ENDPOINT_ANALYZE = "/admin/contracts/contract/auto-intake/analyze/";

  /** 表单字段 → 展示名，用于「已回填」清单 */
  var FIELD_LABELS = {
    name: "合同名称",
    case_type: "合同类型",
    status: "合同状态",
    specified_date: "指定日期",
    start_date: "开始日期",
    end_date: "结束日期",
    fee_mode: "收费模式",
    fixed_amount: "固定/前期律师费",
    risk_rate: "风险比例",
    custom_terms: "自定义收费条款"
  };

  var state = {
    options: null,
    file: null,
    busy: false
  };

  // ── 工具 ────────────────────────────────────────────────────────────

  function $(id) {
    return document.getElementById(id);
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        if (key === "text") {
          node.textContent = attrs[key];
        } else if (key === "html") {
          node.innerHTML = attrs[key];
        } else if (key === "class") {
          node.className = attrs[key];
        } else if (key.indexOf("data-") === 0 || key === "type" || key === "title" || key === "value") {
          node.setAttribute(key, attrs[key]);
        } else {
          node[key] = attrs[key];
        }
      });
    }
    (children || []).forEach(function (child) {
      if (child) node.appendChild(child);
    });
    return node;
  }

  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function humanSize(bytes) {
    if (!bytes) return "0 B";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  // ── 界面骨架 ────────────────────────────────────────────────────────

  function buildPanel() {
    var panel = el("div", { id: "ci-panel", class: "ci-panel" });

    // 头部（可点击折叠）
    var header = el("div", { class: "ci-header" });
    header.appendChild(
      el("span", { class: "ci-header-icon", html: "&#128196;" })
    );
    header.appendChild(
      el("span", { class: "ci-header-title", text: "AI 智能导入合同" })
    );
    header.appendChild(
      el("span", {
        class: "ci-header-hint",
        text: "把合同文件拖到下方，自动解析并填充表单（支持 docx / pdf / txt）"
      })
    );
    var toggle = el("button", {
      type: "button",
      class: "ci-toggle",
      text: "收起"
    });
    header.appendChild(toggle);
    panel.appendChild(header);

    var body = el("div", { class: "ci-body" });

    // 拖拽区
    var drop = el("div", { class: "ci-drop", id: "ci-drop" });
    drop.appendChild(el("div", { class: "ci-drop-icon", html: "&#8681;" }));
    var dropText = el("div", { class: "ci-drop-text" });
    dropText.appendChild(
      el("strong", { text: "拖拽合同文件到这里，或 " })
    );
    var pick = el("button", { type: "button", class: "ci-link-btn", text: "点击选择文件" });
    dropText.appendChild(pick);
    drop.appendChild(dropText);
    drop.appendChild(
      el("div", { class: "ci-drop-sub", text: "一次一份；文件仅用于本次解析，不会归档到合同材料" })
    );
    var fileInput = el("input", {
      type: "file",
      id: "ci-file",
      accept: ".docx,.pdf,.txt,.md",
      style: "display:none"
    });
    drop.appendChild(fileInput);
    body.appendChild(drop);

    // 已选文件 + 模型选择 + 按钮
    var controls = el("div", { class: "ci-controls", id: "ci-controls", style: "display:none" });

    var fileRow = el("div", { class: "ci-file-row" });
    fileRow.appendChild(el("span", { class: "ci-file-name", id: "ci-file-name", text: "" }));
    var clearBtn = el("button", { type: "button", class: "ci-clear-btn", text: "移除", title: "重新选择" });
    fileRow.appendChild(clearBtn);
    controls.appendChild(fileRow);

    var modelRow = el("div", { class: "ci-model-row" });
    modelRow.appendChild(el("label", { class: "ci-model-label", text: "解析模型" }));
    var modelSelect = el("select", { id: "ci-model", class: "ci-model-select" });
    modelRow.appendChild(modelSelect);
    var analyzeBtn = el("button", { type: "button", class: "ci-analyze-btn", id: "ci-analyze", text: "开始分析" });
    modelRow.appendChild(analyzeBtn);
    controls.appendChild(modelRow);

    body.appendChild(controls);

    // 状态区（进度 / 错误 / 结果摘要）
    var status = el("div", { class: "ci-status", id: "ci-status", style: "display:none" });
    body.appendChild(status);

    var result = el("div", { class: "ci-result", id: "ci-result", style: "display:none" });
    body.appendChild(result);

    panel.appendChild(body);

    // 事件
    toggle.addEventListener("click", function () {
      var collapsed = panel.classList.toggle("ci-collapsed");
      toggle.textContent = collapsed ? "展开" : "收起";
    });
    pick.addEventListener("click", function (event) {
      event.preventDefault();
      fileInput.click();
    });
    fileInput.addEventListener("change", function () {
      if (fileInput.files && fileInput.files[0]) {
        setFile(fileInput.files[0]);
      }
    });
    clearBtn.addEventListener("click", function () {
      setFile(null);
    });
    analyzeBtn.addEventListener("click", runAnalyze);

    bindDropZone(drop, fileInput);

    return panel;
  }

  function bindDropZone(drop, fileInput) {
    ["dragenter", "dragover"].forEach(function (name) {
      drop.addEventListener(name, function (event) {
        event.preventDefault();
        event.stopPropagation();
        drop.classList.add("ci-drop-active");
      });
    });
    ["dragleave", "drop"].forEach(function (name) {
      drop.addEventListener(name, function (event) {
        event.preventDefault();
        event.stopPropagation();
        drop.classList.remove("ci-drop-active");
      });
    });
    drop.addEventListener("drop", function (event) {
      var files = event.dataTransfer && event.dataTransfer.files;
      if (!files || !files.length) return;
      // 「一次最多 1 个文件」：取第一个，并明确告知用户多余的已忽略
      if (files.length > 1) {
        showStatus("warning", "一次只能导入一份合同，已选用第一个文件「" + files[0].name + "」");
      }
      setFile(files[0]);
    });
    // 防止拖到页面其它地方时浏览器直接打开文件
    ["dragover", "drop"].forEach(function (name) {
      window.addEventListener(name, function (event) {
        if (event.target === drop || drop.contains(event.target)) return;
        event.preventDefault();
      });
    });
  }

  // ── 文件选择 ────────────────────────────────────────────────────────

  var ALLOWED_EXT = [".docx", ".pdf", ".txt", ".md"];

  function setFile(file) {
    if (file) {
      var name = file.name || "";
      var dot = name.lastIndexOf(".");
      var ext = dot >= 0 ? name.slice(dot).toLowerCase() : "";
      if (ALLOWED_EXT.indexOf(ext) === -1) {
        showStatus("error", "不支持的文件类型「" + (ext || "无扩展名") + "」，请上传 docx / pdf / txt");
        return;
      }
      var maxMb = (state.options && state.options.max_upload_mb) || 50;
      if (file.size > maxMb * 1024 * 1024) {
        showStatus("error", "文件超过 " + maxMb + "MB 上限");
        return;
      }
    }
    state.file = file;
    var controls = $("ci-controls");
    var nameNode = $("ci-file-name");
    if (file) {
      nameNode.textContent = file.name + "（" + humanSize(file.size) + "）";
      controls.style.display = "";
      clearResult();
    } else {
      controls.style.display = "none";
      hideStatus();
      clearResult();
      var input = $("ci-file");
      if (input) input.value = "";
    }
  }

  // ── 状态 / 结果展示 ─────────────────────────────────────────────────

  function showStatus(kind, message) {
    var node = $("ci-status");
    if (!node) return;
    node.className = "ci-status ci-status-" + kind;
    node.textContent = message;
    node.style.display = "";
  }

  function hideStatus() {
    var node = $("ci-status");
    if (node) {
      node.style.display = "none";
      node.textContent = "";
    }
  }

  function clearResult() {
    var node = $("ci-result");
    if (node) {
      node.style.display = "none";
      node.innerHTML = "";
    }
  }

  function setBusy(busy) {
    state.busy = busy;
    var btn = $("ci-analyze");
    var drop = $("ci-drop");
    if (btn) {
      btn.disabled = busy;
      btn.textContent = busy ? "分析中…" : "开始分析";
    }
    if (drop) {
      drop.classList.toggle("ci-drop-busy", busy);
    }
  }

  // ── 分析请求 ────────────────────────────────────────────────────────

  function runAnalyze() {
    if (state.busy) return;
    if (!state.file) {
      showStatus("error", "请先选择一份合同文件");
      return;
    }
    if (state.options && state.options.llm_ready === false) {
      showStatus("error", "系统未配置可用的大模型，请先到「LLM 平台」页面启用一个平台");
      return;
    }

    var form = new FormData();
    form.append("file", state.file);
    var modelSelect = $("ci-model");
    if (modelSelect && modelSelect.value) {
      form.append("model", modelSelect.value);
    }

    setBusy(true);
    clearResult();
    showStatus("loading", "正在解析合同并调用大模型，长合同可能需要 1-2 分钟，请勿关闭页面…");

    fetch(ENDPOINT_ANALYZE, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest"
      },
      body: form,
      credentials: "same-origin"
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, status: res.status, data: data };
        });
      })
      .then(function (payload) {
        if (!payload.data || payload.data.ok !== true) {
          var message = (payload.data && payload.data.error) || "分析失败（HTTP " + payload.status + "）";
          throw new Error(message);
        }
        applyDraft(payload.data.data);
      })
      .catch(function (error) {
        showStatus("error", error.message || "分析失败，请重试");
      })
      .finally(function () {
        setBusy(false);
      });
  }

  // ── 回填 ────────────────────────────────────────────────────────────

  function setFieldValue(name, value) {
    var input = document.getElementById("id_" + name);
    if (!input || value === undefined || value === null || value === "") return false;

    if (input.tagName === "SELECT" && input.multiple) {
      // representation_stages 等多选
      var wanted = Array.isArray(value) ? value : [value];
      Array.prototype.forEach.call(input.options, function (option) {
        option.selected = wanted.indexOf(option.value) !== -1;
      });
    } else {
      input.value = value;
    }
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    markField(input, "ai");
    return true;
  }

  function markField(input, kind) {
    var wrapper = input.closest(".form-row") || input.closest(".field-box") || input.parentNode;
    if (!wrapper) return;
    wrapper.classList.add("ci-filled");
    var badge = wrapper.querySelector(".ci-badge");
    if (!badge) {
      badge = el("span", { class: "ci-badge" });
      var label = wrapper.querySelector("label");
      if (label) {
        label.appendChild(badge);
      } else {
        wrapper.appendChild(badge);
      }
    }
    badge.textContent = kind === "ai" ? "AI 填入" : "需确认";
    badge.classList.toggle("ci-badge-warn", kind !== "ai");
  }

  /**
   * 在 select2 autocomplete 上按名称选中一项。
   *
   * 为什么不能直接设 value：这些字段是 `autocomplete_fields`，select2 维护自己的
   * 选中状态；只改 DOM value 会导致提交值为空。这里先向后端 autocomplete 接口
   * 查一次拿 `{id, text}`，再用 select2 的 `data` 参数真正选中。
   */
  function selectAutocomplete(select, item, done) {
    var $ = window.django && window.django.jQuery;
    if (!select || !item || !item.id) {
      if (done) done(false);
      return;
    }
    if (!$ || !$.fn.select2) {
      // 没有 select2（理论上不会发生）：退回直接赋值
      select.value = String(item.id);
      select.dispatchEvent(new Event("change", { bubbles: true }));
      if (done) done(true);
      return;
    }

    var $select = $(select);
    try {
      if ($select.hasClass("select2-hidden-accessible")) {
        $select.select2("destroy");
      }
      $select.select2({
        data: [{ id: String(item.id), text: item.text }],
        theme: "admin-autocomplete",
        allowClear: true,
        width: "resolve"
      });
      $select.val(String(item.id)).trigger("change");
      // 保持后续仍可使用远程搜索
      $select.on("select2:select", function () {});
      if (done) done(true);
    } catch (error) {
      select.value = String(item.id);
      select.dispatchEvent(new Event("change", { bubbles: true }));
      if (done) done(false);
    }
  }

  /** 用后端 autocomplete 接口按名称查一条记录 */
  function lookupAutocomplete(select, term) {
    var url = select.getAttribute("data-ajax--url");
    if (!url) return Promise.resolve(null);
    var params = new URLSearchParams({
      term: term,
      app_label: select.getAttribute("data-app-label") || "",
      model_name: select.getAttribute("data-model-name") || "",
      field_name: select.getAttribute("data-field-name") || ""
    });
    return fetch(url + "?" + params.toString(), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin"
    })
      .then(function (res) {
        return res.ok ? res.json() : null;
      })
      .then(function (data) {
        if (!data || !data.results || !data.results.length) return null;
        // 优先完全同名，退回第一条
        var exact = data.results.find(function (row) {
          return String(row.text || "").trim() === String(term).trim();
        });
        return exact || data.results[0];
      })
      .catch(function () {
        return null;
      });
  }

  /** 在内联 formset 里加一行，返回该行的容器 */
  function addInlineRow(groupId) {
    var group = document.getElementById(groupId);
    if (!group) return null;
    var link = group.querySelector(".add-row a, .add-row > a");
    if (!link) return null;

    var before = group.querySelectorAll("tr.form-row, .inline-related");
    var beforeLast = before.length ? before[before.length - 1] : null;
    link.click();
    var after = group.querySelectorAll("tr.form-row, .inline-related");
    if (!after.length) return null;
    var added = after[after.length - 1];
    if (added === beforeLast) return null; // 没加成功
    return added;
  }

  /** 往内联表里填一行：先加行，再逐字段赋值 */
  function fillInlineRow(groupId, index, filler) {
    var row = addInlineRow(groupId);
    if (!row) return false;
    filler(row);
    return true;
  }

  function fillParties(parties) {
    if (!parties || !parties.length) return 0;
    var groupId = "contract_parties-group";
    var filled = 0;

    parties.forEach(function (party) {
      var ok = fillInlineRow(groupId, filled, function (row) {
        var clientSelect = row.querySelector('select[name*="-client"]');
        var roleSelect = row.querySelector('select[name*="-role"]');
        if (roleSelect && party.suggested_role) {
          roleSelect.value = party.suggested_role;
          roleSelect.dispatchEvent(new Event("change", { bubbles: true }));
        }
        if (!clientSelect) return;
        if (party.client_id) {
          selectAutocomplete(clientSelect, { id: party.client_id, text: party.client_label || party.name });
        } else {
          // 库内没有此人：在客户端留痕，提示用户先建 Client
          clientSelect.setAttribute("data-ci-missing", party.name);
        }
      });
      if (ok) filled += 1;
    });

    return filled;
  }

  function fillLawyers(lawyers) {
    if (!lawyers || !lawyers.length) return 0;
    var groupId = "contract_assignments-group";
    var filled = 0;

    lawyers.forEach(function (lawyer, index) {
      if (!lawyer.matched && !lawyer.lawyer_id) return;
      var ok = fillInlineRow(groupId, filled, function (row) {
        var lawyerSelect = row.querySelector('select[name*="-lawyer"]');
        var primaryInput = row.querySelector('input[name*="-is_primary"]');
        var orderInput = row.querySelector('input[name*="-order"]');
        if (lawyerSelect && lawyer.lawyer_id) {
          selectAutocomplete(lawyerSelect, {
            id: lawyer.lawyer_id,
            text: lawyer.lawyer_label || lawyer.name
          });
        }
        if (primaryInput) {
          primaryInput.checked = Boolean(lawyer.is_primary) || index === 0;
        }
        if (orderInput) {
          orderInput.value = String(index);
        }
      });
      if (ok) filled += 1;
    });

    return filled;
  }

  function applyDraft(result) {
    var draft = result.draft || {};
    var fields = draft.fields || {};
    var filledFields = [];

    Object.keys(FIELD_LABELS).forEach(function (name) {
      if (fields[name] === undefined) return;
      if (setFieldValue(name, fields[name])) {
        filledFields.push(FIELD_LABELS[name]);
      }
    });

    var partyCount = fillParties(draft.parties || []);
    var lawyerCount = fillLawyers(draft.lawyers || []);

    // 待确认字段打标
    (draft.needs_review || []).forEach(function (key) {
      var input = document.getElementById("id_" + key);
      if (input) markField(input, "warn");
    });

    renderResult(result, {
      filledFields: filledFields,
      partyCount: partyCount,
      lawyerCount: lawyerCount
    });
  }

  function renderResult(result, stats) {
    var node = $("ci-result");
    if (!node) return;
    node.innerHTML = "";
    node.style.display = "";

    var draft = result.draft || {};
    var document_ = result.document || {};

    var head = el("div", { class: "ci-result-head" });
    head.appendChild(el("span", { class: "ci-result-title", text: "分析完成，已回填表单" }));
    head.appendChild(
      el("span", {
        class: "ci-result-meta",
        text: "模型：" + (result.model || "-") + " ｜ 用时：" + (document_.analyzed_at || "-")
      })
    );
    node.appendChild(head);

    // 已回填摘要
    var summary = el("ul", { class: "ci-summary" });
    if (stats.filledFields.length) {
      summary.appendChild(
        el("li", { text: "已填入 " + stats.filledFields.length + " 个字段：" + stats.filledFields.join("、") })
      );
    } else {
      summary.appendChild(el("li", { class: "ci-warn", text: "未能自动填入任何主表字段，请手工填写" }));
    }
    if (stats.partyCount) {
      summary.appendChild(el("li", { text: "已填入 " + stats.partyCount + " 个合同当事人" }));
    }
    if (stats.lawyerCount) {
      summary.appendChild(el("li", { text: "已填入 " + stats.lawyerCount + " 名承办律师" }));
    }
    // 未匹配的当事人
    var unmatchedParties = (draft.parties || []).filter(function (party) {
      return !party.client_id;
    });
    if (unmatchedParties.length) {
      summary.appendChild(
        el("li", {
          class: "ci-warn",
          text:
            "当事人未在系统中找到，需先新增客户后手动选择：" +
            unmatchedParties.map(function (party) {
              return party.name;
            }).join("、")
        })
      );
    }
    var unmatchedLawyers = (draft.lawyers || []).filter(function (lawyer) {
      return !lawyer.lawyer_id;
    });
    if (unmatchedLawyers.length) {
      summary.appendChild(
        el("li", {
          class: "ci-warn",
          text:
            "律师未匹配到系统账号，请手动选择：" +
            unmatchedLawyers.map(function (lawyer) {
              return lawyer.name;
            }).join("、")
        })
      );
    }
    node.appendChild(summary);

    // 告警
    var warnings = result.warnings || [];
    if (warnings.length) {
      var warnBox = el("div", { class: "ci-warnings" });
      warnBox.appendChild(el("div", { class: "ci-warnings-title", text: "请留意：" }));
      var warnList = el("ul");
      warnings.forEach(function (text) {
        warnList.appendChild(el("li", { text: text }));
      });
      warnBox.appendChild(warnList);
      node.appendChild(warnBox);
    }

    node.appendChild(
      el("div", {
        class: "ci-footnote",
        text: "以上内容由 AI 解析生成，请逐项核对后再点击页面下方「保存」。"
      })
    );
  }

  // ── 初始化 ──────────────────────────────────────────────────────────

  function loadOptions(panel) {
    return fetch(ENDPOINT_OPTIONS, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin"
    })
      .then(function (res) {
        return res.ok ? res.json() : null;
      })
      .then(function (payload) {
        if (!payload || payload.ok !== true) return;
        state.options = payload.data || {};
        populateModels(state.options);
        if (state.options.llm_ready === false) {
          showStatus(
            "warning",
            "系统未配置可用的大模型，导入功能暂不可用。请先到「LLM 平台」页面启用平台并配置 API Key。"
          );
        }
      })
      .catch(function () {
        /* 选项加载失败不阻断页面：用户仍可手工录入 */
      });
  }

  function populateModels(options) {
    var select = $("ci-model");
    if (!select) return;
    select.innerHTML = "";
    var models = options.models || [];
    if (!models.length) {
      select.appendChild(el("option", { value: "", text: "（无可用模型）" }));
      return;
    }
    models.forEach(function (model) {
      var option = el("option", { value: model.value, text: model.label });
      select.appendChild(option);
    });

    // 恢复上次选择，否则用默认模型
    var stored = "";
    try {
      stored = window.localStorage.getItem("contract_intake_model") || "";
    } catch (error) {
      stored = "";
    }
    var hasStored = models.some(function (model) {
      return model.value === stored;
    });
    select.value = hasStored ? stored : options.default_model || models[0].value;

    select.addEventListener("change", function () {
      try {
        window.localStorage.setItem("contract_intake_model", select.value);
      } catch (error) {
        /* 隐私模式下 localStorage 不可用，忽略 */
      }
    });
  }

  function init() {
    // 只在「新建合同」页挂载（change 页 original 存在，不挂）
    if (!document.getElementById("id_name")) return;
    if (document.getElementById("ci-panel")) return;

    var container = document.querySelector("#content > h1") || document.querySelector("#content");
    if (!container || !container.parentNode) return;

    var panel = buildPanel();
    // 插到 #content 顶部（标题之后、表单之前）
    var content = document.getElementById("content");
    if (content) {
      content.insertBefore(panel, content.firstChild);
    }

    loadOptions(panel);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
