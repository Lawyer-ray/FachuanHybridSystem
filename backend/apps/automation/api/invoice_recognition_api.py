"""Compatibility shim for moved invoice recognition API."""

from apps.invoice_recognition.api.invoice_recognition_api import router

__all__ = ["router"]

