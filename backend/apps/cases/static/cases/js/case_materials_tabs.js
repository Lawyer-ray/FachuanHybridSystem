(function () {
  'use strict';

  function getCsrfToken() {
    if (window.FachuanCSRF && window.FachuanCSRF.getToken) return window.FachuanCSRF.getToken() || '';
    const tokenElement = document.querySelector('[name=csrfmiddlewaretoken]');
    if (tokenElement && tokenElement.value) return tokenElement.value;
    const cookies = document.cookie ? document.cookie.split(';') : [];
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.startsWith('csrftoken=')) return cookie.substring('csrftoken='.length);
    }
    return '';
  }

  function toast(message, type) {
    window.dispatchEvent(new CustomEvent('case-detail-toast', { detail: { message, type } }));
  }

  function loadSortable(callback) {
    if (typeof Sortable !== 'undefined') {
      callback();
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js';
    script.onload = callback;
    document.head.appendChild(script);
  }

  function parseTime(value) {
    if (!value) return 0;
    const t = Date.parse(value);
    return Number.isFinite(t) ? t : 0;
  }

  function applyTimeOrder(tabEl, order) {
    const lists = tabEl.querySelectorAll('[data-material-file-list]');
    lists.forEach(function (listEl) {
      const items = Array.from(listEl.querySelectorAll('.material-file'));
      items.sort(function (a, b) {
        const ta = parseTime(a.getAttribute('data-uploaded-at'));
        const tb = parseTime(b.getAttribute('data-uploaded-at'));
        return order === 'desc' ? tb - ta : ta - tb;
      });
      items.forEach(function (el) {
        listEl.appendChild(el);
      });
    });
  }

  function initTimeToggle() {
    const caseId = window.CASE_ID;
    const tabs = document.querySelectorAll('[data-materials-tab]');
    tabs.forEach(function (tabEl) {
      const tabKey = tabEl.getAttribute('data-materials-tab') || 'tab';
      const storageKey = `caseMaterialsOrder:${caseId}:${tabKey}`;
      const button = tabEl.querySelector('[data-material-sort-toggle]');
      const current = localStorage.getItem(storageKey) || 'asc';
      applyTimeOrder(tabEl, current);
      if (button) {
        button.textContent = current === 'desc' ? '时间：倒序' : '时间：正序';
        button.addEventListener('click', function () {
          const next = (localStorage.getItem(storageKey) || 'asc') === 'asc' ? 'desc' : 'asc';
          localStorage.setItem(storageKey, next);
          applyTimeOrder(tabEl, next);
          button.textContent = next === 'desc' ? '时间：倒序' : '时间：正序';
        });
      }
    });
  }

  function saveGroupOrder(container) {
    const caseId = window.CASE_ID;
    if (!caseId) return;
    const category = container.getAttribute('data-category') || '';
    const side = container.getAttribute('data-side') || null;
    const supervisingAuthorityId = container.getAttribute('data-supervising-authority-id') || null;
    const orderedTypeIds = Array.from(container.querySelectorAll('.material-group'))
      .map(function (el) {
        const raw = el.getAttribute('data-type-id');
        const val = raw ? parseInt(raw, 10) : NaN;
        return Number.isFinite(val) ? val : null;
      })
      .filter(function (x) {
        return x;
      });

    if (!orderedTypeIds.length) return;

    const payload = {
      category: category,
      ordered_type_ids: orderedTypeIds,
      side: side,
      supervising_authority_id: supervisingAuthorityId ? parseInt(supervisingAuthorityId, 10) : null,
    };

    fetch(`/api/v1/cases/${caseId}/materials/group-order`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
      },
      body: JSON.stringify(payload),
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error('save failed');
        toast('已保存排序', 'success');
      })
      .catch(function () {
        toast('保存排序失败', 'error');
      });
  }

  function initSortable() {
    const containers = document.querySelectorAll('[data-material-group-list]');
    if (!containers.length) return;
    loadSortable(function () {
      containers.forEach(function (container) {
        new Sortable(container, {
          handle: '.material-group-handle',
          animation: 150,
          ghostClass: 'sortable-ghost',
          onEnd: function () {
            saveGroupOrder(container);
          },
        });
      });
    });
  }

  function stripExtension(name) {
    const raw = (name || '').trim();
    const idx = raw.lastIndexOf('.');
    if (idx <= 0) return raw;
    const ext = raw.slice(idx + 1);
    if (!ext || ext.length > 5) return raw;
    if (!/^[a-z0-9]+$/i.test(ext)) return raw;
    return raw.slice(0, idx);
  }

  function normalizeFileNames() {
    const nodes = document.querySelectorAll('.material-file-name');
    nodes.forEach(function (el) {
      const raw = (el.textContent || '').trim();
      if (!raw) return;
      const stripped = stripExtension(raw);
      if (stripped !== raw) {
        el.setAttribute('title', raw);
        el.textContent = stripped;
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    normalizeFileNames();
    initTimeToggle();
    initSortable();
  });
})();
