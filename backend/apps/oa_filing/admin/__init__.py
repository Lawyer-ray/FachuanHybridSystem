from django.contrib import admin

from apps.oa_filing.models import FilingSession, StampSession

from .filing_session_admin import FilingSessionAdmin
from .stamp_session_admin import StampSessionAdmin

admin.site.register(FilingSession, FilingSessionAdmin)
admin.site.register(StampSession, StampSessionAdmin)
