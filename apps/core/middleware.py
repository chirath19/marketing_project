"""Core middleware."""

import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.core.request_context import set_request_id

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    """Attach a correlation id to each request and echo it back.

    An inbound `X-Request-ID` is trusted only for correlation (never for
    authorisation) and is length-capped so a hostile client cannot inflate
    every log line.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")[:64].strip()
        request_id = incoming or uuid.uuid4().hex
        request.request_id = request_id
        set_request_id(request_id)

        response = self.get_response(request)
        response[REQUEST_ID_HEADER] = request_id
        return response
