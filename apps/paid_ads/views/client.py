"""Read-only metrics for the selected, subscribed client organization."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import render

from apps.paid_ads import policies, selectors
from apps.paid_ads.forms import FilterForm


@login_required
def workspace(request):
    organization = request.organization
    if request.user.is_staff_member or not policies.can_read(request.user, organization):
        raise PermissionDenied("This organization's active services do not include Paid Ads.")
    form = FilterForm(request.GET, actor=request.user, organization=organization)
    context = {
        "page_title": "Paid advertising",
        "portal_key": "paid_ads",
        "organization": organization,
        "filter_form": form,
    }
    if form.is_valid():
        context.update(selectors.report(request.user, organization, form.cleaned_data))
        context["daily_page"] = Paginator(context["daily_rows"], 31).get_page(
            request.GET.get("page")
        )
    query = request.GET.copy()
    query.pop("page", None)
    context["querystring"] = query.urlencode()
    return render(
        request, "paid_ads/client/workspace.html", context, status=200 if form.is_valid() else 400
    )
