/* 法穿 AI 桥（后台插件，isVisual:false）
   职责：文档内核 ↔ 法穿页面。**不带任何 UI**。

   ★ 架构：文档适配器（DocAdapter）
   ---------------------------------------------------------------
   「AI 出建议 → 律师决策 → 落痕」这个范式与文档类型无关；
   只有「怎么在文档内核里定位与写入」是类型相关的。
   所以本文件把类型差异收敛到 ADAPTERS，页面与左栏完全不用改。

     WordAdapter  docx   —— Search → Select → ReplaceTextSmart      （一期，已真机验证）
     CellAdapter  xlsx   —— 定位单元格 → SetValue（修订模式）        （二期）
     SlideAdapter pptx   —— 定位 shape → textFrame 改写              （三期，视需要）
     PdfAdapter   pdf    —— 只批注，不支持修订（明确返回 unsupported） （三期）

   适配器接口（实现几个就算几个）：
     ready()                        → bool         当前类型是否支持
     locate(anchor, hint)           → {ok, found}
     apply({orig, sug, hint})       → {ok, how?, reason?}
     bulk(accept)                   → {ok}
     insertAtSelection(text)        → {ok}

   ★ 两条实测红线（踩过，别改回去）
   1) callCommand 第二参必须 false。传 true 会让插件 iframe 直接被销毁，
      回调永远拿不到 —— 表现为「点采纳没反应、不报错」。
   2) Asc.scope 只能可靠地传 **字符串**。传对象时回调静默丢失；
      统一用 Asc.scope.key = JSON.stringify(payload)。
   -------------------------------------------------------------- */
(function (window, undefined) {
  var pageWin = (window.parent && window.parent.parent && window.parent.parent !== window)
    ? window.parent.parent : window.parent;

  function post(msg) {
    try { pageWin.postMessage(Object.assign({ source: "fachuan-plugin" }, msg), "*"); } catch (e) {}
  }

  /* ---------- 公共：只在 callCommand 内可用（Api 对象只存在于内核上下文） ---------- */

  function editorType() {
    try { return (window.Asc.plugin.info && window.Asc.plugin.info.editorType) || "word"; } catch (e) { return "word" }
  }

  /* 在每个 callCommand 内注入的工具函数（字符串模板，避免闭包丢失） */
  var KERNEL_HELPERS = [
    "function __find(doc, anchor) {",
    "  var rs = doc.Search(anchor);",
    "  if (rs && rs.length) { rs[0].Select(); return { ok: true, how: 'search', n: rs.length }; }",
    "  var n = doc.GetElementsCount();",
    "  for (var i = 0; i < n; i++) {",
    "    var el = doc.GetElement(i);",
    "    try { if (el.GetText && el.GetText().indexOf(anchor) >= 0) { el.GetRange().Select(); return { ok: true, how: 'element' }; } } catch (e) {}",
    "  }",
    "  return { ok: false, how: 'none' };",
    "}"
  ].join("\n");

  /* 把 helper + 业务语句拼成一个无闭包依赖的函数（callCommand 会把它序列化到内核里执行） */
  function kernelFn(lines) {
    /* eslint-disable no-new-func */
    return new Function(KERNEL_HELPERS + "\ntry {\n" + lines.join("\n") + "\n} catch (e) { return { ok: false, reason: String(e.message || e) }; }");
    /* eslint-enable no-new-func */
  }

  var ADAPTERS = {

    /* ---------------- Word（docx）---------------- */
    word: {
      ready: function () { return editorType() === "word" },
      locate: function (payload, done) {
        Asc.scope.key = JSON.stringify(payload);
        window.Asc.plugin.callCommand(kernelFn([
          "var s = JSON.parse(Asc.scope.key);",
          "return __find(Api.GetDocument(), s.orig);"
        ]), false);
      },
      apply: function (payload, done) {
        Asc.scope.key = JSON.stringify(payload);
        window.Asc.plugin.callCommand(kernelFn([
          "var s = JSON.parse(Asc.scope.key);",
          "var doc = Api.GetDocument();",
          "doc.SetTrackRevisions(true);",              /* 关键：先开修订模式 */
          "var hit = __find(doc, s.orig);",
          "if (!hit.ok) return { ok: false, reason: '原文未找到（可能已被改写）' };",
          "Api.ReplaceTextSmart([s.sug], false, true);",
          "return { ok: true, how: hit.how, n: hit.n || 1 };"
        ]), false);
      },
      bulk: function (accept, done) {
        Asc.scope.key = accept ? "1" : "0";
        window.Asc.plugin.callCommand(kernelFn([
          "var doc = Api.GetDocument();",
          "if (Asc.scope.key === '1') doc.AcceptAllRevisionChanges(); else doc.RejectAllRevisionChanges();",
          "return { ok: true };"
        ]), false);
      },
      insertAtSelection: function (text) {
        window.Asc.plugin.callCommand(function () {
          try { Api.GetDocument().SetTrackRevisions(true); return { ok: true } } catch (e) { return { ok: false } }
        }, false);
        window.Asc.plugin.executeMethod("InsertAndReplaceContent", [{ text: text }], function () {
          post({ type: "inserted", text: text });
        });
      }
    },

    /* ---------------- Excel（xlsx）—— 二期 ---------------- */
    cell: {
      ready: function () { return editorType() === "cell" },
      /* 合同/材料场景里 Excel 的「建议」通常是「某单元格的值应改为 X」，
         锚点用 A1 地址而不是文本搜索（文本可能重复，单元格地址唯一）。 */
      locate: function (payload, done) {
        Asc.scope.key = JSON.stringify({ cell: payload.cell || payload.orig });
        window.Asc.plugin.callCommand(function () {
          try {
            var s = JSON.parse(Asc.scope.key);
            var ws = Api.GetActiveSheet();
            var r = ws.GetRange(s.cell);
            r.Select();
            return { ok: !!r };
          } catch (e) { return { ok: false, reason: String(e.message || e) }; }
        }, false);
      },
      apply: function (payload, done) {
        Asc.scope.key = JSON.stringify(payload);
        window.Asc.plugin.callCommand(function () {
          try {
            var s = JSON.parse(Asc.scope.key);
            var ws = Api.GetActiveSheet();
            ws.GetRange(s.cell).SetValue(s.sug);
            return { ok: true, how: "cell" };
          } catch (e) { return { ok: false, reason: String(e.message || e) }; }
        }, false);
      },
      bulk: function (accept, done) { done && done({ ok: false, reason: "cell 类型暂不支持批量修订" }) },
      insertAtSelection: function (text) { post({ type: "inserted", error: "cell 类型请用单元格地址写入" }) }
    },

    /* ---------------- PowerPoint（pptx）—— 三期 ---------------- */
    slide: {
      ready: function () { return editorType() === "slide" },
      locate: function (payload, done) { done && done({ ok: false, reason: "slide 类型暂未实现" }) },
      apply: function (payload, done) { done && done({ ok: false, reason: "slide 类型暂未实现" }) },
      bulk: function (accept, done) { done && done({ ok: false, reason: "slide 类型暂未实现" }) },
      insertAtSelection: function (text) { post({ type: "inserted", error: "slide 类型暂未实现" }) }
    },

    /* ---------------- PDF —— 只批注，不改正文 ---------------- */
    pdf: {
      ready: function () { return editorType() === "pdf" },
      locate: function (payload, done) { done && done({ ok: false, reason: "PDF 不支持修订，请改用批注" }) },
      apply: function (payload, done) { done && done({ ok: false, reason: "PDF 不支持修订，请改用批注" }) },
      bulk: function (accept, done) { done && done({ ok: false, reason: "PDF 不支持修订" }) },
      insertAtSelection: function (text) { post({ type: "inserted", error: "PDF 不支持修订，请改用批注" }) }
    }
  };

  function adapter() {
    var t = editorType();
    return ADAPTERS[t] || null;
  }

  /* 统一出口：所有需要回调的 action 都走这里（保证 onCommandCallback 只装一次） */
  var pendingAction = null;
  function runWithCallback(fn, payload, kind) {
    var ad = adapter();
    if (!ad) { post({ type: kind, result: { ok: false, reason: "不支持的文档类型：" + editorType() } }); return }
    var finished = false;
    window.Asc.plugin.onCommandCallback = function (res) {
      finished = true;
      post({ type: kind, result: res || { ok: false, reason: "no-callback" }, id: payload && payload.id });
    };
    try {
      fn(ad, payload, function (res) {              /* 适配器内部直接完成的（如 unsupported） */
        if (finished) return;
        finished = true;
        post({ type: kind, result: res, id: payload && payload.id });
      });
    } catch (e) {
      if (!finished) post({ type: kind, result: { ok: false, reason: String(e.message || e) }, id: payload && payload.id });
      return;
    }
    setTimeout(function () {                         /* 兜底：3s 无回调则报错，避免「一直转」 */
      if (!finished) { finished = true; post({ type: kind, result: { ok: false, reason: "内核无响应（超时）" }, id: payload && payload.id }) }
    }, 3000);
  }

  /* ---------- 选区 ---------- */
  function getSelection(explicit) {
    try {
      window.Asc.plugin.executeMethod("GetSelectedText", null, function (text) {
        if (text && typeof text === "object") text = text.text || text.data || "";
        pushSelection(String(text || "").trim(), explicit);
      });
    } catch (e) {}
  }
  var lastSel = undefined;
  function pushSelection(text, explicit) {
    if (text === lastSel && !explicit) return;
    lastSel = text;
    post({ type: "selection", text: text, explicit: !!explicit });
  }
  function watchSelection() {
    try { window.Asc.plugin.attachEvent && window.Asc.plugin.attachEvent("onSelectionChanged", function () { getSelection() }) } catch (e) {}
    try { window.Asc.plugin.attachEvent && window.Asc.plugin.attachEvent("onClick", function () { getSelection() }) } catch (e) {}
    setInterval(function () { getSelection() }, 700);
  }

  /* ---------- 协议入口 ---------- */
  window.addEventListener("message", function (e) {
    var d = e.data;
    if (!d || d.source !== "fachuan-page") return;
    var ad = adapter();

    if (d.action === "hello") {                       /* 页面握手：返回类型与支持能力 */
      post({ type: "hello", editorType: editorType(), supported: !!(ad && ad.ready()) });
      return;
    }
    if (d.action === "get-selection") { getSelection(true); return; }
    if (d.action === "insert-revision") {
      if (ad) ad.insertAtSelection(String(d.text || ""));
      return;
    }
    if (d.action === "locate") {
      runWithCallback(function (a, p, done) {
        p = { orig: String(d.text || "") };
        if (!a.ready()) return done({ ok: false, reason: "不支持的文档类型" });
        a.locate(p, done);
      }, { orig: d.text }, "located");
      return;
    }
    if (d.action === "apply-revision") {
      runWithCallback(function (a, p, done) {
        if (!a.ready()) return done({ ok: false, reason: "不支持的文档类型" });
        a.apply(p, done);
      }, d.payload || {}, "applied");
      return;
    }
    if (d.action === "accept-all" || d.action === "reject-all") {
      var accept = d.action === "accept-all";
      runWithCallback(function (a, p, done) {
        if (!a.ready()) return done({ ok: false, reason: "不支持的文档类型" });
        a.bulk(accept, done);
      }, {}, "done");
      return;
    }
  });

  /* ---------- 生命周期 ---------- */
  window.Asc.plugin.init = function () {
    try {
      window.Asc.plugin.executeMethod("AddContextMenuItem", [{
        guid: window.Asc.plugin.guid,
        items: [{ id: "fachuanAiRewrite", text: "✦ AI 改写选中内容" }]
      }]);
    } catch (e) {}
    post({ type: "ready", editorType: editorType(), supported: !!(adapter() && adapter().ready()) });
    watchSelection();
  };
  window.Asc.plugin.button = function () { window.Asc.plugin.executeCommand("close", "") };
  window.Asc.plugin.onContextMenuClick = function (id) {
    if (id === "fachuanAiRewrite" || (id && id.id === "fachuanAiRewrite")) getSelection();
  };
})(window, undefined);
