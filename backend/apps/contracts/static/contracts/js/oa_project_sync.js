/**
 * 新建合同页「同步」按钮：按律所ID（OA 案件 GUID）拉取 OA 案件详情并回填表单。
 *
 * 纯接口、无浏览器：后端用当前登录人的 OA 凭证 GET projectView 详情页
 * （客户 / 案件信息 / 利冲三个 tab 服务端一次性渲染），整形后回填：
 * - 普通字段（合同名称 / 合同类型 / 开始日期 / 律所OA案件编号 / 律所OA链接 / 律所ID）直接赋值
 * - 当事人（委托人 ← 客户信息；对方 ← 利冲对立方）与承办律师（← 案件负责人）
 *   直接使用后端解析好的 Client id 填 inline 行；本地缺失的当事人后端已按阵营
 *   自动建库（委托人＝我方，其余＝非我方），无需先去建客户
 *
 * 阵营口径：只有 OA「客户信息」tab 的委托人才是我方当事人；利冲表里与「代理何方」
 * 同法律地位的共同被告 / 共同原告只是同案其他当事人，不是我们的委托人，只提示不填。
 *
 * 仅新建页注入（模板按 original 为空才写 window.CONTRACT_OA_SYNC_URL）。
 * 成功静默（结果内联汇总），仅请求级失败红字提示，不弹窗。
 */
(function () {
    'use strict';

    var SYNC_URL = window.CONTRACT_OA_SYNC_URL;
    if (!SYNC_URL) return;

    var BTN_STYLE = 'margin-left:8px;padding:4px 12px;font-size:13px;cursor:pointer;'
        + 'border:1px solid var(--fc-border-input);border-radius:4px;'
        + 'background:var(--fc-bg-muted-light);color:var(--fc-text-secondary);vertical-align:middle;';
    var AUTOCOMPLETE_BASE = '/admin/autocomplete/?app_label=contracts&model_name=';
    var ADD_ROW_SETTLE_MS = 120;

    function init() {
        var guidField = document.getElementById('id_law_firm_oa_guid');
        if (!guidField) return;

        var syncBtn = document.createElement('button');
        syncBtn.type = 'button';
        syncBtn.textContent = '同步';
        syncBtn.title = '用当前登录人的律所OA账号读取该律所ID对应的案件详情，回填合同名称、类型、日期、当事人与承办律师';
        syncBtn.style.cssText = BTN_STYLE;
        // 紧贴 input 之后（「查询ID」的结果框也挂在同一父节点，不能用 appendChild）
        guidField.insertAdjacentElement('afterend', syncBtn);

        var resultBox = document.createElement('div');
        resultBox.style.cssText = 'margin-top:6px;font-size:12px;line-height:1.8;';
        guidField.parentNode.appendChild(resultBox);

        syncBtn.addEventListener('click', function () {
            onSync(guidField, syncBtn, resultBox);
        });
    }

    function onSync(guidField, syncBtn, resultBox) {
        var guid = (guidField.value || '').trim();
        if (!guid) {
            renderNote(resultBox, '请先填写律所ID（可用「查询ID」按律所OA案件编号自动获取）', 'muted');
            return;
        }
        var form = document.querySelector('#content-main form');
        var csrfInput = form ? form.querySelector('input[name="csrfmiddlewaretoken"]') : null;
        if (!csrfInput) {
            renderNote(resultBox, '未找到 CSRF 令牌，请刷新页面重试', 'error');
            return;
        }

        setBusy(syncBtn, true);
        renderNote(resultBox, '正在读取律所OA案件详情…', 'muted');
        fetch(SYNC_URL, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfInput.value },
            body: JSON.stringify({ guid: guid })
        })
            .then(function (resp) {
                return resp.json().then(function (data) { return { status: resp.status, data: data }; });
            })
            .then(function (payload) {
                if (!(payload.data && payload.data.ok && payload.data.data)) {
                    setBusy(syncBtn, false);
                    renderNote(resultBox, (payload.data && payload.data.error) || ('同步失败（HTTP ' + payload.status + '）'), 'error');
                    return;
                }
                renderNote(resultBox, '已读取案件详情，正在匹配当事人与律师…', 'muted');
                return applyPayload(payload.data.data, guidField).then(function (report) {
                    setBusy(syncBtn, false);
                    renderSummary(resultBox, report);
                });
            })
            .catch(function () {
                setBusy(syncBtn, false);
                renderNote(resultBox, '同步请求失败，请检查网络后重试', 'error');
            });
    }

    function setBusy(btn, busy) {
        btn.disabled = busy;
        btn.textContent = busy ? '同步中…' : '同步';
    }

    // ── 回填 ──

    async function applyPayload(data, guidField) {
        var filled = [];
        if (setInput('id_name', data.name)) filled.push('合同名称');
        if (setSelect('id_case_type', data.case_type)) filled.push('合同类型');
        if (setInput('id_start_date', data.start_date)) filled.push('开始日期');
        if (setMultiSelect('id_representation_stages', data.representation_stages)) filled.push('代理阶段');
        if (setSelect('id_fee_mode', data.fee_mode)) filled.push('收费模式');
        if (setInput('id_fixed_amount', data.fixed_amount)) filled.push('律师费金额');
        if (setInput('id_custom_terms', data.custom_terms)) filled.push('自定义收费条款');
        if (setInput('id_law_firm_oa_case_number', data.case_number)) filled.push('律所OA案件编号');
        if (setInput('id_law_firm_oa_url', data.detail_url)) filled.push('律所OA链接');
        if (data.guid && data.guid !== guidField.value) {
            guidField.value = data.guid;
            guidField.dispatchEvent(new Event('change', { bubbles: true }));
        }

        var principals = await fillParties(data.clients || [], 'PRINCIPAL', null);
        var opponents = await fillParties(data.opponents || [], 'OPPOSING', 'conflict_type');
        var lawyer = await fillLawyer(data.responsible_lawyer || '');
        return { filled: filled, principals: principals, opponents: opponents, lawyer: lawyer, data: data };
    }

    function setInput(id, value) {
        var el = document.getElementById(id);
        if (!el || !value) return false;
        el.value = value;
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
    }

    // 枚举值不在 options 里（后端映射不到或 choices 变了）就不动已有值
    function setSelect(id, value) {
        var el = document.getElementById(id);
        if (!el || !value) return false;
        if (!el.querySelector('option[value="' + value + '"]')) return false;
        el.value = value;
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
    }

    // 多选（代理阶段）：追加选中，不清已有选项；一个都对不上就不动
    function setMultiSelect(id, values) {
        var el = document.getElementById(id);
        if (!el || !values || !values.length) return false;
        var hit = false;
        for (var i = 0; i < el.options.length; i++) {
            if (values.indexOf(el.options[i].value) >= 0) {
                el.options[i].selected = true;
                hit = true;
            }
        }
        if (hit) el.dispatchEvent(new Event('change', { bubbles: true }));
        return hit;
    }

    // ── 当事人 ──

    // 逐个填行（保持 OA 顺序；单个失败只记未匹配不中断）。
    // 后端已把当事人解析成 Client id（缺失已按阵营自动建库），这里直接用；
    // 仅在解析失败时回退 autocomplete 兜底。typeKey 指定展示用的附注字段
    //（对方当事人带法律地位：「某机关（被告）」）
    async function fillParties(items, role, typeKey) {
        var report = { matched: [], missing: [], failed: [], created: [] };
        for (var i = 0; i < items.length; i++) {
            var item = items[i] || {};
            var name = (item.name || '').trim();
            if (!name) continue;
            var label = typeKey && item[typeKey] ? name + '（' + item[typeKey] + '）' : name;
            try {
                var client = resolveClient(item);
                if (!client) client = await lookupAutocomplete('contractparty', 'client', name);
                if (!client) { report.missing.push(label); continue; }
                if (isClientSelected(client.id)) { report.matched.push(label); continue; }
                if (!(await fillPartyRow(client, role))) { report.failed.push(label); continue; }
                report.matched.push(label);
                if (item.created) report.created.push(label);
            } catch (e) {
                report.failed.push(label);
            }
        }
        return report;
    }

    // 后端解析结果（client_id / client_name）优先，避免再查一次 autocomplete
    function resolveClient(item) {
        if (!item.client_id) return null;
        return { id: item.client_id, text: item.client_name || item.name || '' };
    }

    // 经 admin autocomplete 查库，全名精确优先，唯一包含关系兜底（与「解析」同口径）。
    // Django 6 的 AutocompleteJsonView 只认 term（q 回退已移除）
    function lookupAutocomplete(modelName, fieldName, term) {
        var url = AUTOCOMPLETE_BASE + modelName + '&field_name=' + fieldName + '&term=' + encodeURIComponent(term);
        return fetch(url, { credentials: 'same-origin' }).then(function (resp) {
            if (!resp.ok) throw new Error('autocomplete ' + resp.status);
            return resp.json();
        }).then(function (data) {
            var results = (data && data.results) || [];
            var exact = results.filter(function (r) { return r.text === term; });
            if (exact.length) return exact[0];
            var fuzzy = results.filter(function (r) {
                return r.text.indexOf(term) >= 0 || term.indexOf(r.text) >= 0;
            });
            return fuzzy.length === 1 ? fuzzy[0] : null;
        });
    }

    function isClientSelected(clientId) {
        var value = String(clientId);
        var sels = liveSelects('select[name^="contract_parties-"][name$="-client"]');
        for (var i = 0; i < sels.length; i++) {
            if (sels[i].value === value) return true;
        }
        return false;
    }

    // 填一个 client 为空的当事人行并置角色；没空行先点「添加另一条」增行。
    // admin autocomplete 的 select 初始只有空 option，直接赋 value 会静默落空——
    // 必须先注入真实 option 再选中并派发 change（Select2 据此渲染标签）。
    async function fillPartyRow(client, role) {
        var sel = await ensureEmptySelect(
            'select[name^="contract_parties-"][name$="-client"]',
            '#contract_parties-group .add-row a'
        );
        if (!sel) return false;
        chooseOption(sel, client.id, client.text);
        var row = sel.closest('.form-row, .dynamic-contract_parties, fieldset.module, tr');
        var roleSelect = row ? row.querySelector('select[name$="-role"]') : null;
        if (roleSelect) {
            roleSelect.value = role;
            roleSelect.dispatchEvent(new Event('change', { bubbles: true }));
        }
        return true;
    }

    // ── 承办律师 ──

    async function fillLawyer(name) {
        var report = { name: name, matched: false, missing: false, failed: false };
        if (!name) return report;
        try {
            var lawyer = await lookupAutocomplete('contractassignment', 'lawyer', name);
            if (!lawyer) { report.missing = true; return report; }
            if (isLawyerSelected(lawyer.id)) { report.matched = true; return report; }
            var sel = await ensureEmptySelect(
                'select[name^="assignments-"][name$="-lawyer"]',
                '#assignments-group .add-row a'
            );
            if (!sel) { report.failed = true; return report; }
            chooseOption(sel, lawyer.id, lawyer.text);
            var row = sel.closest('.form-row, .dynamic-assignments, fieldset.module, tr');
            var primary = row ? row.querySelector('input[name$="-is_primary"]') : null;
            if (primary && !primary.checked) {
                primary.checked = true;
                primary.dispatchEvent(new Event('change', { bubbles: true }));
            }
            report.matched = true;
        } catch (e) {
            report.failed = true;
        }
        return report;
    }

    function isLawyerSelected(lawyerId) {
        var value = String(lawyerId);
        var sels = liveSelects('select[name^="assignments-"][name$="-lawyer"]');
        for (var i = 0; i < sels.length; i++) {
            if (sels[i].value === value) return true;
        }
        return false;
    }

    // ── inline 通用 ──

    // 排除隐藏空模板行（name 含 __prefix__ / .empty-form）：填进去既不可见也不会
    // 随表单提交，且会被 add-row 克隆污染新行
    function liveSelects(selector) {
        var out = [];
        var sels = document.querySelectorAll(selector);
        for (var i = 0; i < sels.length; i++) {
            if (sels[i].name.indexOf('__prefix__') >= 0) continue;
            if (sels[i].closest('.empty-form')) continue;
            out.push(sels[i]);
        }
        return out;
    }

    function firstEmptySelect(selector) {
        var sels = liveSelects(selector);
        for (var i = 0; i < sels.length; i++) {
            if (!sels[i].value) return sels[i];
        }
        return null;
    }

    async function ensureEmptySelect(selector, addLinkSelector) {
        var sel = firstEmptySelect(selector);
        if (sel) return sel;
        var addLink = document.querySelector(addLinkSelector);
        if (!addLink) return null;
        addLink.click();  // inlines.js 同步克隆空表单并初始化新行控件
        await new Promise(function (resolve) { setTimeout(resolve, ADD_ROW_SETTLE_MS); });
        return firstEmptySelect(selector);
    }

    function chooseOption(sel, id, text) {
        var value = String(id);
        if (!sel.querySelector('option[value="' + value + '"]')) {
            var opt = document.createElement('option');
            opt.value = value;
            opt.textContent = text;
            sel.appendChild(opt);
        }
        sel.value = value;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
    }

    // ── 结果展示 ──

    var TONE_COLOR = {
        muted: 'var(--fc-text-muted, #666)',
        error: 'var(--fc-danger, #ba2121)',
        success: 'var(--fc-success, #2e7d32)'
    };

    function renderNote(box, message, tone) {
        box.innerHTML = '';
        box.appendChild(line(message, tone));
    }

    function line(message, tone) {
        var el = document.createElement('div');
        el.style.color = TONE_COLOR[tone] || TONE_COLOR.muted;
        el.textContent = message;
        return el;
    }

    function renderSummary(box, report) {
        box.innerHTML = '';
        if (report.filled.length) {
            box.appendChild(line('✓ 已同步：' + report.filled.join('、'), 'success'));
        } else {
            box.appendChild(line('OA 详情中没有可回填的基础字段', 'muted'));
        }
        // OA 详情页（PROJECT002 视图，含全部 tab）实测不展示案件编号，只有列表页才有；
        // 主流程「先填案号 → 查询ID → 同步」案号已在手，直接贴 GUID 同步时提醒手动补
        var caseNoField = document.getElementById('id_law_firm_oa_case_number');
        if (!report.data.case_number && caseNoField && !(caseNoField.value || '').trim()) {
            box.appendChild(line('OA 详情页不含案件编号，请手动填写「律所OA案件编号」', 'muted'));
        }
        appendPartyLines(box, '委托人', report.principals, report.data.clients || []);
        appendPartyLines(box, '对方当事人', report.opponents, report.data.opponents || []);
        // OA 利冲表列的是全部相关方。与「代理何方」同法律地位（共同被告 / 共同原告等）
        // 只是同案其他当事人，不是律所的委托人；第三人同样不是我方——两组都只提示不填
        appendInfoList(box, '同案其他当事人（非我方当事人，未回填，按需手动添加）', report.data.co_parties || []);
        appendInfoList(box, '第三人（非我方当事人，未回填）', report.data.third_parties || []);
        var hasMissing = report.principals.missing.length > 0 || report.opponents.missing.length > 0;
        if (hasMissing && report.data.auto_create_allowed === false) {
            box.appendChild(line('当前账号无当事人新增权限，未能自动建库；请手动新建当事人后选择', 'error'));
        }
        appendLawyerLine(box, report.lawyer);
        var extras = [];
        if (report.data.case_stage) extras.push('案件阶段：' + report.data.case_stage);
        if (report.data.client_side) extras.push('代理何方：' + report.data.client_side);
        if (report.data.fee_currency && report.data.fee_currency !== '人民币') extras.push('币种：' + report.data.fee_currency);
        if (extras.length) box.appendChild(line('OA 参考：' + extras.join('；'), 'muted'));
    }

    function appendPartyLines(box, label, report, source) {
        if (!source.length) return;
        if (report.matched.length) {
            var createdNote = report.created.length ? '（其中 ' + report.created.join('、') + ' 已在当事人库自动新建）' : '';
            box.appendChild(line(label + '已填：' + report.matched.join('、') + createdNote, 'success'));
        }
        if (report.missing.length) {
            box.appendChild(line(label + '未匹配：' + report.missing.join('、') + '（未能自动建库，请手动新建后选择）', 'error'));
        }
        if (report.failed.length) {
            box.appendChild(line(label + '未能填入：' + report.failed.join('、') + '（无可用行或查询客户库失败）', 'error'));
        }
    }

    function appendLawyerLine(box, report) {
        if (!report.name) return;
        if (report.matched) {
            box.appendChild(line('承办律师已填：' + report.name + '（主办）', 'success'));
        } else if (report.missing) {
            box.appendChild(line('承办律师未匹配：' + report.name + '（本地无同名律师，请手动选择）', 'error'));
        } else if (report.failed) {
            box.appendChild(line('承办律师未能填入：' + report.name + '（无可用行或查询失败）', 'error'));
        }
    }

    function appendInfoList(box, label, items) {
        if (!items.length) return;
        var text = items.map(function (it) {
            var position = it.conflict_type ? '（' + it.conflict_type + '）' : '';
            var created = it.created ? '，已建库' : '';
            return it.name + position + created;
        }).join('、');
        box.appendChild(line(label + '：' + text, 'muted'));
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
