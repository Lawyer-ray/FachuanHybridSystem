from django.contrib import admin

from apps.oa_filing.models import ArchiveSession, FilingSession, StampSession

from .archive_session_admin import ArchiveSessionAdmin
from .filing_session_admin import FilingSessionAdmin
from .stamp_session_admin import StampSessionAdmin

admin.site.register(ArchiveSession, ArchiveSessionAdmin)
admin.site.register(FilingSession, FilingSessionAdmin)
admin.site.register(StampSession, StampSessionAdmin)
