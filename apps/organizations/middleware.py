"""Current-organization resolution.

`request.organization` is the organization the current session is working
in. It is resolved **server-side from the signed-in user's memberships**
and never from a path segment, query parameter or header — a slug in a
request is an intention, not an entitlement.

Staff do not belong to client organizations, so `request.organization` is
None for them; staff views take the organization from the URL and check it
through a policy, which is a different rule and deliberately a different
code path.

The attribute is lazy: pages that never mention an organization — the
public site, sign-in, the health check — cost no query.

**Test it for truthiness, never with `is None`.** A `SimpleLazyObject`
wrapping None is an object, so `request.organization is None` is always
False and a guard written that way silently lets a staff user through to
code that assumes a client. `if not request.organization` proxies to
`bool(None)` and gives the right answer; `has_organization()` below says
the same thing more clearly.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.utils.functional import SimpleLazyObject

from apps.organizations import selectors

SESSION_KEY = "active_organization_id"


def _resolve(request: HttpRequest):  # noqa: ANN202
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_client:
        return None

    available = selectors.organizations_for_user(user)

    # A previously chosen organization is honoured only if the user still
    # belongs to it. Re-checking rather than trusting the session is what
    # stops access surviving a membership being removed.
    chosen_id = request.session.get(SESSION_KEY)
    if chosen_id:
        chosen = available.filter(pk=chosen_id).first()
        if chosen is not None:
            return chosen
        request.session.pop(SESSION_KEY, None)

    return selectors.primary_organization_for(user)


def has_organization(request: HttpRequest) -> bool:
    """Whether this request has a client organization in scope.

    Written as a helper so no caller has to remember why `is None` is the
    wrong test here.
    """
    return bool(getattr(request, "organization", None))


class CurrentOrganizationMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.organization = SimpleLazyObject(lambda: _resolve(request))
        return self.get_response(request)
