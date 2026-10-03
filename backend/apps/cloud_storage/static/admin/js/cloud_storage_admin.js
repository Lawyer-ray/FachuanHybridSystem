/**
 * CloudStorageAccount admin — show/hide fieldsets + help sections based on storage_type,
 * and move auth sections into their respective fieldsets.
 */
document.addEventListener('DOMContentLoaded', function () {
  var typeSelect = document.getElementById('id_storage_type');
  if (!typeSelect) return;

  var sectionMap = {
    local: { fieldset: 'local-section' },
    webdav: { fieldset: 'webdav-section' },
    onedrive: { fieldset: 'onedrive-section' },
    s3: { fieldset: 's3-section' },
    google_drive: { fieldset: 'gdrive-section' },
    dropbox: { fieldset: 'dropbox-section' },
  };

  function toggle() {
    var val = typeSelect.value;
    Object.entries(sectionMap).forEach(function (entry) {
      var key = entry[0];
      var cfg = entry[1];

      // Toggle fieldset
      var el = document.querySelector('.' + cfg.fieldset);
      if (el) {
        var wrapper = el.closest('.grp-group') || el.closest('fieldset') || el;
        wrapper.style.display = key === val ? '' : 'none';
      }
    });

    // Toggle help sections
    var helpSections = [
      { id: 'nutstore-help-section', type: 'webdav' },
      { id: '123pan-help-section', type: 'webdav' },
      { id: 'onedrive-help-section', type: 'onedrive' },
      { id: 's3-help-section', type: 's3' },
      { id: 'gdrive-help-section', type: 'google_drive' },
      { id: 'dropbox-help-section', type: 'dropbox' },
    ];
    helpSections.forEach(function (section) {
      var el = document.getElementById(section.id);
      if (el) el.style.display = val === section.type ? '' : 'none';
    });
  }

  typeSelect.addEventListener('change', toggle);
  toggle();

  // Move auth sections into their respective fieldsets
  var authSections = [
    { id: 'onedrive-auth-section', headingContains: 'OneDrive' },
    { id: 'dropbox-auth-section', headingContains: 'Dropbox' },
  ];

  authSections.forEach(function (cfg) {
    var authSection = document.getElementById(cfg.id);
    if (!authSection) return;

    var fieldsets = document.querySelectorAll('fieldset');
    for (var i = 0; i < fieldsets.length; i++) {
      var heading = fieldsets[i].querySelector('h2');
      if (heading && heading.textContent.indexOf(cfg.headingContains) !== -1) {
        authSection.style.margin = '12px 0 0 0';
        authSection.style.padding = '12px';
        authSection.style.borderTop = '1px solid var(--fc-border)';
        fieldsets[i].appendChild(authSection);
        break;
      }
    }
  });
});
