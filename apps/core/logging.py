"""Logging helpers."""

import logging

from apps.core.request_context import get_request_id


class RequestIDFilter(logging.Filter):
    """Stamp every record with the current request's correlation id.

    Lets a single user action be followed across log lines, which matters
    once the platform is one process serving public pages, dashboards and
    the API at the same time.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True
