"""Personal notification inbox and lightweight dashboard badge updates."""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.notifications import selectors, services


@login_required
@never_cache
@require_GET
def summary(request):
    return JsonResponse(selectors.activity_summary(request.user))


@login_required
@never_cache
@require_GET
def inbox(request):
    page = Paginator(selectors.for_user(request.user), 30).get_page(request.GET.get("page", 1))
    return render(
        request,
        "notifications/inbox.html",
        {
            "shell": "admin/base.html" if request.user.is_staff_member else "portal/base.html",
            "page_title": "Notifications",
            "page_subtitle": "Messages, enquiries and updates for you.",
            "nav_key": "notifications",
            "portal_key": "notifications",
            "page_obj": page,
        },
    )


@login_required
@require_POST
def read_all(request):
    services.mark_all_read(user=request.user)
    return redirect("notifications:inbox")


@login_required
@require_POST
def open_notification(request, pk):
    notification = selectors.get_for_user(request.user, pk)
    if notification is None:
        raise Http404
    notification.mark_read()
    target = notification.url
    if (
        target
        and target.startswith("/")
        and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        )
    ):
        return redirect(target)
    return redirect("notifications:inbox")
