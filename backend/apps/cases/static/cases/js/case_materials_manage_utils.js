/**
 * case_materials_manage_utils.js
 * Standalone utility functions for the case materials management page.
 * Must be loaded BEFORE case_materials_manage.js.
 */
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

  function formatTime(value) {
    const t = Date.parse(value);
    if (!Number.isFinite(t)) return '';
    const d = new Date(t);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function normalizeCandidate(candidate, prefill, defaultCategory, supervisingAuthorities) {
    const material = candidate.material || null;
    const draft = prefill || {};
    const draftPartyIds = Array.isArray(draft.party_ids) ? draft.party_ids.map(String) : [];
    const draftAuthorityId = draft.supervising_authority_id ? String(draft.supervising_authority_id) : '';
    const dc = ['party', 'non_party'].includes(defaultCategory) ? defaultCategory : '';
    const materialCategory = material ? (material.category || '') : '';
    const singleAuthorityId = (supervisingAuthorities || []).length === 1 ? String(supervisingAuthorities[0].id) : '';
    const row = {
      attachmentId: candidate.attachment_id,
      fileName: candidate.file_name,
      fileUrl: candidate.file_url,
      uploadedAt: candidate.uploaded_at,
      uploadedAtDisplay: formatTime(candidate.uploaded_at),
      isBound: Boolean(material),
      materialId: material ? material.id : null,
      category: materialCategory || (draft.category || dc || ''),
      lastCategory: materialCategory || (draft.category || dc || ''),
      side: material ? (material.side || '') : (draft.side || (dc === 'party' ? 'our' : '')),
      partyIds: material ? (material.party_ids || []).map(String) : draftPartyIds,
      supervisingAuthorityId: material ? (material.supervising_authority_id || '') : draftAuthorityId,
      typeSelect: material && material.type_id ? String(material.type_id) : '',
      customTypeName: material && !material.type_id ? (material.type_name || '') : (draft.type_name_hint || ''),
    };
    // 非当事人材料且只有一个主管机关时，自动选择
    if (row.category === 'non_party' && !row.supervisingAuthorityId && singleAuthorityId) {
      row.supervisingAuthorityId = singleAuthorityId;
    }
    if (!row.typeSelect && row.customTypeName) row.typeSelect = '__custom__';
    return row;
  }

  function readQueryValue(name) {
    try {
      const url = new URL(window.location.href);
      return url.searchParams.get(name) || '';
    } catch (_) {
      return '';
    }
  }

  function mergeFiles(existing, incoming) {
    const seen = new Set();
    const all = [];
    const push = (f) => {
      if (!f) return;
      const key = `${f.name || ''}__${String(f.size || 0)}__${String(f.lastModified || 0)}`;
      if (seen.has(key)) return;
      seen.add(key);
      all.push(f);
    };
    (existing || []).forEach(push);
    (incoming || []).forEach(push);
    return all;
  }

  // Expose utilities on a namespace for the other files to consume
  window.CaseMaterialsUtils = {
    getCsrfToken: getCsrfToken,
    formatTime: formatTime,
    normalizeCandidate: normalizeCandidate,
    readQueryValue: readQueryValue,
    mergeFiles: mergeFiles,
  };
})();
