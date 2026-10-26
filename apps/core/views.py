"""Core views: health, error pages and the component styleguide."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import requires_csrf_token

from apps.core import styleguide_data
from apps.core.forms import StyleguideDemoForm

logger = logging.getLogger(__name__)


@never_cache
def health(request: HttpRequest) -> JsonResponse:
    """Liveness and readiness for the Railway healthcheck.

    The database round-trip is included deliberately: a web process that
    cannot reach Postgres is not ready to take traffic, and returning 200
    in that state would let a broken deploy replace a working one. The
    error detail is logged, never returned, so the endpoint cannot leak
    connection strings to an unauthenticated caller.
    """
    checks: dict[str, str] = {}
    healthy = True

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception:
        logger.exception("Health check: database unreachable")
        checks["database"] = "error"
        healthy = False

    return JsonResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status=200 if healthy else 503,
    )


def styleguide(request: HttpRequest) -> HttpResponse:
    """Every component in every state, on one page.

    This is the responsive and accessibility check surface for each
    phase. It is staff-only in production because it reveals the full
    component inventory.
    """
    if not settings.DEBUG and not request.user.is_staff:
        raise Http404

    return render(request, "styleguide.html", {
        "demo_form": StyleguideDemoForm(),
        "bound_form": StyleguideDemoForm(data={"full_name": "", "work_email": "not-an-email"}),
        "services": styleguide_data.SERVICES,
        "clients": styleguide_data.CLIENTS,
        "campaigns": styleguide_data.CAMPAIGNS,
        "leads": styleguide_data.LEADS,
        "approvals": styleguide_data.APPROVALS,
        "reports": styleguide_data.REPORTS,
        "activity": styleguide_data.ACTIVITY,
        "notifications": styleguide_data.NOTIFICATIONS,
        "inbox": styleguide_data.INBOX,
        "campaign_columns": styleguide_data.CAMPAIGN_COLUMNS,
        "filter_tabs": styleguide_data.FILTER_TABS,
        "billing_options": styleguide_data.BILLING_OPTIONS,
        "breadcrumb_items": styleguide_data.BREADCRUMBS,
        "demo_page": styleguide_data.demo_page(),
    })


# --- Error handlers --------------------------------------------------------
#
# Registered in config/urls.py. Each renders a branded page; none echoes
# any part of the request back into the response.


def bad_request(request: HttpRequest, exception) -> HttpResponse:  # noqa: ANN001
    return render(request, "errors/400.html", status=400)


def permission_denied(request: HttpRequest, exception) -> HttpResponse:  # noqa: ANN001
    return render(request, "errors/403.html", status=403)


def page_not_found(request: HttpRequest, exception) -> HttpResponse:  # noqa: ANN001
    return render(request, "errors/404.html", status=404)


def server_error(request: HttpRequest) -> HttpResponse:
    # Rendered with an empty context: context processors do not run here,
    # so errors/500.html must not depend on any of them.
    return render(request, "errors/500.html", status=500)


@requires_csrf_token
def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    logger.warning("CSRF failure on %s: %s", request.path, reason)
    return render(request, "errors/403_csrf.html", status=403)
