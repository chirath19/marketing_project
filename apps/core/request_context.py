"""Request-scoped state, kept out of global variables.

A `ContextVar` is used rather than thread locals so the same code works
under ASGI, where a single thread serves many concurrent requests.
"""

from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    return _request_id.get()
