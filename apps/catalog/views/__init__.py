"""Catalogue views: the public pages, and the staff screens that edit them."""

from apps.catalog.views import admin
from apps.catalog.views.public import (
    quote_add,
    quote_clear,
    quote_remove,
    quote_review,
    service_detail,
    services_category,
    services_index,
)

__all__ = [
    "admin", "quote_add", "quote_clear", "quote_remove", "quote_review",
    "service_detail", "services_category", "services_index",
]
