"""Admin-managed switches for optional platform features."""

from django import forms
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.core import operations
from apps.core.features import FEATURES, MASTER_FIELDS
from apps.core.forms import StyledForm
from apps.permissions.guards import require_permission


class OperatingForm(StyledForm):
    def __init__(self, *args, **kwargs):
        flags = kwargs.pop("flags", {})
        super().__init__(*args, **kwargs)
        for key, (label, default, parent) in FEATURES.items():
            if key not in MASTER_FIELDS:
                self.fields[f"feature_{key}"] = forms.BooleanField(
                    required=False, label=label, initial=flags.get(key, default),
                    help_text=f"Requires {FEATURES[parent][0]} to be enabled." if parent else "",
                )

    integrations_enabled = forms.BooleanField(
        required=False,
        label="Enable external integrations",
        help_text=(
            "Allow Meta, Google and other provider syncs. "
            "Credentials and saved data are retained when off."
        ),
    )
    api_enabled = forms.BooleanField(
        required=False,
        label="Enable the application API",
        help_text=(
            "Allow authenticated access to /api/. The website and client portal work without it."
        ),
    )
    analytics_enabled = forms.BooleanField(
        required=False,
        label="Enable website analytics",
        help_text="Enable analytics collection, consent controls and configured tracking tags.",
    )
    show_public_prices = forms.BooleanField(
        required=False,
        label="Show catalogue prices publicly",
        help_text=(
            "When off, visitors request a tailored quotation. "
            "Staff can still set prices and publish proposals."
        ),
    )
    require_quote_account = forms.BooleanField(
        required=False,
        label="Prefer account-based quotation requests",
        help_text=("Send the main quote entry to sign-in. The explicit guest entry remains "
                   "available at /quote/?guest=1."),
    )


@require_permission("settings_manage")
@require_http_methods(["GET", "POST"])
def settings_view(request):
    obj = operations.current()
    form = OperatingForm(
        request.POST if request.method == "POST" else None,
        initial={key: getattr(obj, key) for key in OperatingForm.base_fields},
        flags=obj.feature_flags,
    )
    if request.method == "POST" and form.is_valid():
        values = {key: value for key, value in form.cleaned_data.items()
                  if not key.startswith("feature_")}
        values["feature_flags"] = {key.removeprefix("feature_"): value
                                   for key, value in form.cleaned_data.items()
                                   if key.startswith("feature_")}
        operations.update(actor=request.user, values=values)
        messages.success(
            request, "Operating settings saved. Existing records and credentials are retained."
        )
        return redirect("staff:module_settings")
    return render(
        request,
        "staff/operating.html",
        {
            "page_title": "Operating settings",
            "nav_key": "settings",
            "form": form,
            "groups": [
                ("Operating mode", [form[key] for key in MASTER_FIELDS.values()]),
                ("Catalogue and quotations", [form["show_public_prices"],
                                               form["require_quote_account"]]),
                ("Provider connections", [form[f"feature_{key}"] for key, value in
                                          FEATURES.items() if value[2] == "integrations"]),
                ("Website tracking tags", [form[f"feature_{key}"] for key, value in
                                           FEATURES.items() if value[2] == "analytics"]),
                ("Client workspaces", [form[f"feature_{key}"] for key, value in
                                       FEATURES.items() if not value[2] and
                                       key not in MASTER_FIELDS]),
            ],
            "page_subtitle": "Start manually and enable integrations when ready.",
        },
    )
