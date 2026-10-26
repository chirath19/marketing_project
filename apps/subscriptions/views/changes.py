from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.catalog.selectors import live_services
from apps.core.forms import StyledForm
from apps.permissions.guards import require_permission
from apps.subscriptions import changes, selectors
from apps.subscriptions.guards import require_client_module


class ChangeForm(StyledForm):
    kind = forms.ChoiceField(
        choices=[
            ("renewal", "Renewal"),
            ("extension", "Duration extension"),
            ("extra", "Extra deliverables"),
            ("additional", "Additional service"),
        ]
    )
    requirements = forms.CharField(max_length=5000, widget=forms.Textarea(attrs={"rows": 5}))
    requested_end = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Required for renewals and extensions.",
    )
    additional_service = forms.ModelChoiceField(queryset=None, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["additional_service"].queryset = live_services().filter(can_request_quote=True)


@login_required
@require_client_module("service_requests")
@require_http_methods(["GET", "POST"])
def client_create(request, pk):
    if not request.user.is_client:
        raise Http404
    subscription = selectors.client_subscription(request.user, pk)
    if not subscription or subscription.organization_id != getattr(
        request.organization, "pk", None
    ):
        raise Http404
    from apps.core.features import require

    require("service_requests", request.user)
    form = ChangeForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            change = changes.request_change(
                actor=request.user, subscription=subscription, **form.cleaned_data
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect("organizations:quote_detail", pk=change.quote_id)
    return render(
        request,
        "subscriptions/client/change_form.html",
        {
            "form": form,
            "subscription": subscription,
            "portal_key": "service_requests",
        },
    )


@login_required
@require_client_module("service_requests")
def client_list(request):
    if not request.user.is_client:
        raise Http404
    return render(
        request,
        "subscriptions/changes.html",
        {
            "shell": "portal/base.html",
            "requests": changes.visible(request.user, request.organization),
            "portal_key": "service_requests",
            "page_title": "Service requests",
        },
    )


@require_permission("subscriptions_view")
def staff_list(request):
    return render(
        request,
        "subscriptions/changes.html",
        {
            "shell": "admin/base.html",
            "requests": changes.visible(request.user),
            "staff_desk": True,
            "page_title": "Service requests",
            "nav_key": "service_requests",
        },
    )


@require_permission("subscriptions_approve")
@require_http_methods(["POST"])
def staff_apply(request, pk):
    change = changes.visible(request.user).filter(pk=pk).first()
    if not change:
        raise Http404
    try:
        changes.apply(actor=request.user, request_id=change.pk)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, "The accepted change is now reflected in the service history.")
    return redirect("staff:service_requests")
