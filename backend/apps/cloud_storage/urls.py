"""URL configuration for cloud_storage admin endpoints."""

from django.urls import path

from .api import dropbox_complete_auth, dropbox_start_auth, onedrive_complete_auth, onedrive_start_auth

app_name = "cloud_storage"

urlpatterns = [
    path("<int:account_id>/onedrive/start-auth/", onedrive_start_auth, name="onedrive_start_auth"),
    path("<int:account_id>/onedrive/complete-auth/", onedrive_complete_auth, name="onedrive_complete_auth"),
    path("<int:account_id>/dropbox/start-auth/", dropbox_start_auth, name="dropbox_start_auth"),
    path("<int:account_id>/dropbox/complete-auth/", dropbox_complete_auth, name="dropbox_complete_auth"),
]
