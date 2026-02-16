"""Django admin configuration."""

from . import document, document_delivery, document_recognition, insurance, scraper, sms, token

__all__: list[str] = [
    "document",
    "document_delivery",
    "document_recognition",
    "insurance",
    "scraper",
    "sms",
    "token",
]
