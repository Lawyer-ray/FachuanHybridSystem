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
        listEl.appendChild(el.parentElement);
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

  // ========== 分组重命名功能 ==========

  window.startRenameGroup = function (titleEl) {
    if (!titleEl) return;
    // 避免重复进入编辑模式
    if (titleEl.querySelector('input')) return;

    var typeId = titleEl.getAttribute('data-group-type-id');
    var currentName = titleEl.getAttribute('data-group-type-name') || titleEl.textContent.trim();
    if (!typeId) return;

    var input = document.createElement('input');
    input.type = 'text';
    input.value = currentName;
    input.className = 'material-group-rename-input';
    input.setAttribute('data-original-name', currentName);

    titleEl.textContent = '';
    titleEl.appendChild(input);
    input.focus();
    input.select();

    // 隐藏编辑按钮
    var renameBtn = titleEl.parentElement.querySelector('.material-group-rename-btn');
    if (renameBtn) renameBtn.style.display = 'none';

    function finishRename() {
      var newName = (input.value || '').trim();
      var originalName = input.getAttribute('data-original-name');

      // 恢复显示
      titleEl.textContent = newName || originalName;
      if (renameBtn) renameBtn.style.display = '';

      if (!newName || newName === originalName) {
        if (!newName) titleEl.textContent = originalName;
        return;
      }

      // 调用 API 重命名
      var caseId = window.CASE_ID;
      fetch(`/api/v1/cases/${caseId}/materials/group-rename`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({
          type_id: parseInt(typeId, 10),
          new_type_name: newName,
          update_global: false,
        }),
      })
        .then(function (resp) {
          if (!resp.ok) return resp.json().then(function (data) { throw new Error(data.detail || '重命名失败'); });
          return resp.json();
        })
        .then(function (data) {
          titleEl.textContent = data.new_type_name;
          titleEl.setAttribute('data-group-type-name', data.new_type_name);
          toast('分组已重命名', 'success');
        })
        .catch(function (err) {
          titleEl.textContent = originalName;
          titleEl.setAttribute('data-group-type-name', originalName);
          toast(err.message || '重命名失败', 'error');
        });
    }

    input.addEventListener('blur', finishRename);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        input.blur();
      } else if (e.key === 'Escape') {
        input.value = input.getAttribute('data-original-name');
        input.blur();
      }
    });
  };

  // ========== 替换材料文件功能 ==========

  var replaceState = {
    materialId: null,
    caseId: null,
  };

  // 创建一个隐藏的 file input，复用而非每次新建
  var replaceFileInput = document.createElement('input');
  replaceFileInput.type = 'file';
  replaceFileInput.style.display = 'none';
  document.body.appendChild(replaceFileInput);

  window.startReplaceMaterial = function (btn) {
    replaceState.materialId = btn.getAttribute('data-material-id');
    replaceState.caseId = btn.getAttribute('data-case-id');

    replaceFileInput.value = '';
    replaceFileInput.click();
  };

  replaceFileInput.addEventListener('change', function () {
    var files = replaceFileInput.files;
    if (!files || !files.length) return;
    if (!replaceState.caseId || !replaceState.materialId) {
      toast('参数错误', 'error');
      return;
    }

    toast('正在替换文件...', 'success');

    // Step 1: 上传文件到案件日志
    var fd = new FormData();
    fd.append('files', files[0]);

    fetch(`/api/v1/cases/${replaceState.caseId}/materials/upload`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken() },
      body: fd,
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error('上传失败');
        return resp.json();
      })
      .then(function (uploadData) {
        var attachmentIds = uploadData.attachment_ids || [];
        if (!attachmentIds.length) throw new Error('未获取到附件ID');
        var newAttachmentId = attachmentIds[0];

        // Step 2: 替换材料的附件
        return fetch(`/api/v1/cases/${replaceState.caseId}/materials/${replaceState.materialId}/replace`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
          },
          body: JSON.stringify({ new_attachment_id: newAttachmentId }),
        });
      })
      .then(function (resp) {
        if (!resp.ok) return resp.json().then(function (data) { throw new Error(data.detail || '替换失败'); });
        return resp.json();
      })
      .then(function () {
        toast('材料文件已替换，正在刷新...', 'success');
        setTimeout(function () { window.location.reload(); }, 800);
      })
      .catch(function (err) {
        toast(err.message || '替换失败', 'error');
      });
  });

  // ========== 删除材料功能 ==========

  var deleteState = {
    materialId: null,
    caseId: null,
    rowEl: null,
  };

  window.confirmDeleteMaterial = function (btn) {
    deleteState.materialId = btn.getAttribute('data-material-id');
    deleteState.caseId = btn.getAttribute('data-case-id');
    deleteState.rowEl = btn.closest('.material-file-row');

    var modal = document.getElementById('materialDeleteModal');
    if (modal) modal.style.display = 'flex';
  };

  window.closeDeleteModal = function () {
    var modal = document.getElementById('materialDeleteModal');
    if (modal) modal.style.display = 'none';
    deleteState.materialId = null;
    deleteState.caseId = null;
    deleteState.rowEl = null;
  };

  window.doDeleteMaterial = function () {
    if (!deleteState.caseId || !deleteState.materialId) {
      toast('参数错误', 'error');
      return;
    }

    var confirmBtn = document.getElementById('materialDeleteConfirmBtn');
    if (confirmBtn) confirmBtn.disabled = true;

    fetch(`/api/v1/cases/${deleteState.caseId}/materials/${deleteState.materialId}`, {
      method: 'DELETE',
      headers: { 'X-CSRFToken': getCsrfToken() },
    })
      .then(function (resp) {
        if (!resp.ok) return resp.json().then(function (data) { throw new Error(data.detail || '删除失败'); });
        return resp.json();
      })
      .then(function () {
        toast('材料已删除，正在刷新...', 'success');
        window.closeDeleteModal();
        setTimeout(function () { window.location.reload(); }, 600);
      })
      .catch(function (err) {
        toast(err.message || '删除失败', 'error');
        if (confirmBtn) confirmBtn.disabled = false;
      });
  };

  // ========== 删除全部材料功能 ==========

  var deleteAllState = {
    caseId: null,
    category: null,
  };

  window.confirmDeleteAllMaterials = function (btn) {
    deleteAllState.caseId = btn.getAttribute('data-case-id');
    deleteAllState.category = btn.getAttribute('data-category');

    var descEl = document.getElementById('deleteAllModalDesc');
    var categoryLabel = deleteAllState.category === 'party' ? '当事人材料' : '非当事人材料';
    if (descEl) {
      descEl.textContent = '确定要删除当前案件下所有「' + categoryLabel + '」吗？删除后分类绑定和附件文件都将被移除，此操作不可恢复。';
    }

    var modal = document.getElementById('materialDeleteAllModal');
    if (modal) modal.style.display = 'flex';
  };

  window.closeDeleteAllModal = function () {
    var modal = document.getElementById('materialDeleteAllModal');
    if (modal) modal.style.display = 'none';
    deleteAllState.caseId = null;
    deleteAllState.category = null;
  };

  window.doDeleteAllMaterials = function () {
    if (!deleteAllState.caseId || !deleteAllState.category) {
      toast('参数错误', 'error');
      return;
    }

    var confirmBtn = document.getElementById('materialDeleteAllConfirmBtn');
    if (confirmBtn) confirmBtn.disabled = true;

    fetch('/api/v1/cases/' + deleteAllState.caseId + '/materials', {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
      },
      body: JSON.stringify({ category: deleteAllState.category }),
    })
      .then(function (resp) {
        if (!resp.ok) return resp.json().then(function (data) { throw new Error(data.detail || '删除失败'); });
        return resp.json();
      })
      .then(function (data) {
        toast('已删除 ' + data.deleted_count + ' 条材料，正在刷新...', 'success');
        window.closeDeleteAllModal();
        setTimeout(function () { window.location.reload(); }, 600);
      })
      .catch(function (err) {
        toast(err.message || '删除失败', 'error');
        if (confirmBtn) confirmBtn.disabled = false;
      });
  };

  document.addEventListener('DOMContentLoaded', function () {
    normalizeFileNames();
    initTimeToggle();
    initSortable();
  });
})();
