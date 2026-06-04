/**
 * CloudStorageAccount admin — show/hide fieldsets + help sections based on storage_type,
 * and move OneDrive auth section into the OneDrive fieldset.
 */
document.addEventListener('DOMContentLoaded', function () {
  var typeSelect = document.getElementById('id_storage_type');
  if (!typeSelect) return;

  var sectionMap = {
    local: { fieldset: 'local-section', help: 'nutstore-help-section' },
    webdav: { fieldset: 'webdav-section', help: 'nutstore-help-section' },
    onedrive: { fieldset: 'onedrive-section', help: 'onedrive-help-section' },
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

    // Toggle help sections — show all WebDAV guides when webdav is selected
    var helpSections = [
      { id: 'nutstore-help-section', type: 'webdav' },
      { id: '123pan-help-section', type: 'webdav' },
      { id: 'onedrive-help-section', type: 'onedrive' },
    ];
    helpSections.forEach(function (section) {
      var el = document.getElementById(section.id);
      if (el) el.style.display = val === section.type ? '' : 'none';
    });
  }

  typeSelect.addEventListener('change', toggle);
  toggle();

  // Move OneDrive auth section into the OneDrive fieldset
  var authSection = document.getElementById('onedrive-auth-section');
  if (!authSection) return;

  var fieldsets = document.querySelectorAll('fieldset');
  for (var i = 0; i < fieldsets.length; i++) {
    var heading = fieldsets[i].querySelector('h2');
    if (heading && heading.textContent.indexOf('OneDrive') !== -1) {
      authSection.style.margin = '12px 0 0 0';
      authSection.style.padding = '12px';
      authSection.style.borderTop = '1px solid #eee';
      fieldsets[i].appendChild(authSection);
      break;
    }
  }
});
