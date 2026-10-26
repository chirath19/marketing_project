"""The staff screens that manage the service catalogue.

A service has more to it than a collection row — features, packages, a
comparison matrix, two different kinds of switch — so it gets its own
editor. Categories and add-ons ride the generic collection views already
built for the CMS.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.catalog import selectors, services
from apps.catalog.forms import (
    ServiceAddonForm,
    ServiceFeatureForm,
    ServiceForm,
    ServicePackageForm,
)
from apps.catalog.models import Service, ServiceAddon, ServiceFeature, ServicePackage
from apps.permissions.guards import require_permission

CATALOG_BREADCRUMB = [{"label": "Services", "href": "/staff/services/"}]


def _shell(title: str, subtitle: str = "", **extra) -> dict:
    return {"page_title": title, "page_subtitle": subtitle,
            "nav_key": "services", **extra}


@require_permission("catalog_view")
def service_list(request: HttpRequest) -> HttpResponse:
    """Everything, including retired and hidden — this is the editor's view."""
    return render(request, "catalog/admin/list.html", _shell(
        "Service catalogue", "What the agency sells, and what it shows.",
        services=selectors.all_services(),
        categories=selectors.live_categories(),
        columns=[{"label": "Service"}, {"label": "Category"},
                 {"label": "Price", "align": "right"}, {"label": "Status"},
                 {"label": "", "align": "right", "sr_label": "Actions"}],
    ))


@require_permission("catalog_create")
@require_http_methods(["GET", "POST"])
def service_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ServiceForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                service = services.save_catalog_object(
                    form=form, actor=request.user, created=True)
            except ValidationError as exc:
                for message in exc.messages:
                    form.add_error(None, message)
            else:
                messages.success(request, _("Service created. It is hidden "
                                            "until you show it."))
                return redirect("staff:catalog_service", pk=service.pk)
    else:
        form = ServiceForm()

    return render(request, "catalog/admin/service_form.html", _shell(
        "New service", "It stays hidden from the public until you show it.",
        form=form, creating=True, breadcrumbs=CATALOG_BREADCRUMB,
    ))


@require_permission("catalog_view")
@require_http_methods(["GET", "POST"])
def service_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """The service editor.

    Opened with `catalog_view`; the service layer then requires
    `catalog_edit` to save, so a viewer can look without changing.
    """
    service = get_object_or_404(
        Service.objects.prefetch_related("features", "packages", "addons"), pk=pk
    )

    if request.method == "POST":
        form = ServiceForm(request.POST, request.FILES, instance=service)
        if form.is_valid():
            try:
                services.save_catalog_object(form=form, actor=request.user)
            except ValidationError as exc:
                for message in exc.messages:
                    form.add_error(None, message)
            else:
                messages.success(request, _("Service saved."))
                return redirect("staff:catalog_service", pk=service.pk)
    else:
        form = ServiceForm(instance=service)

    return render(request, "catalog/admin/service_form.html", _shell(
        service.name, f"/services/{service.slug}/",
        service=service, form=form,
        features=service.features.all().order_by("order", "pk"),
        packages=service.packages.all().order_by("order", "pk"),
        feature_form=ServiceFeatureForm(),
        package_form=ServicePackageForm(),
        breadcrumbs=CATALOG_BREADCRUMB,
    ))


@require_permission("catalog_publish")
@require_http_methods(["POST"])
def service_visibility(request: HttpRequest, pk: int) -> HttpResponse:
    service = get_object_or_404(Service, pk=pk)
    services.set_service_visibility(service=service, actor=request.user,
                                    visible=request.POST.get("visible") == "1")
    messages.success(request, _("Updated."))
    return redirect("staff:catalog_service", pk=service.pk)


@require_permission("catalog_publish")
@require_http_methods(["POST"])
def service_active(request: HttpRequest, pk: int) -> HttpResponse:
    service = get_object_or_404(Service, pk=pk)
    services.set_service_active(service=service, actor=request.user,
                                active=request.POST.get("active") == "1")
    messages.success(request, _("Updated."))
    return redirect("staff:catalog_service", pk=service.pk)


@require_permission("catalog_edit")
@require_http_methods(["POST"])
def service_move(request: HttpRequest, pk: int) -> HttpResponse:
    service = get_object_or_404(Service, pk=pk)
    services.move(instance=service, actor=request.user,
                  direction=request.POST.get("direction", "up"))
    return redirect("staff:module_services")


@require_permission("catalog_delete")
@require_http_methods(["POST"])
def service_delete(request: HttpRequest, pk: int) -> HttpResponse:
    service = get_object_or_404(Service, pk=pk)
    services.delete_catalog_object(instance=service, actor=request.user)
    messages.success(request, _("Service deleted."))
    return redirect("staff:module_services")


# --- features ----------------------------------------------------------------


@require_permission("catalog_create")
@require_http_methods(["POST"])
def feature_create(request: HttpRequest, pk: int) -> HttpResponse:
    service = get_object_or_404(Service, pk=pk)
    form = ServiceFeatureForm(request.POST)

    if form.is_valid():
        form.instance.service = service
        services.save_catalog_object(form=form, actor=request.user, created=True)
        messages.success(request, _("Feature added."))
    else:
        messages.error(request, _("That feature could not be added."))

    return redirect("staff:catalog_service", pk=service.pk)


@require_permission("catalog_delete")
@require_http_methods(["POST"])
def feature_delete(request: HttpRequest, pk: int) -> HttpResponse:
    feature = get_object_or_404(ServiceFeature, pk=pk)
    service_id = feature.service_id
    services.delete_catalog_object(instance=feature, actor=request.user)
    return redirect("staff:catalog_service", pk=service_id)


# --- packages ----------------------------------------------------------------


@require_permission("catalog_create")
@require_http_methods(["POST"])
def package_create(request: HttpRequest, pk: int) -> HttpResponse:
    service = get_object_or_404(Service, pk=pk)
    form = ServicePackageForm(request.POST)

    if form.is_valid():
        form.instance.service = service
        try:
            services.save_catalog_object(form=form, actor=request.user, created=True)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, _("Package added."))
    else:
        messages.error(request, _("That package could not be added."))

    return redirect("staff:catalog_service", pk=service.pk)


@require_permission("catalog_view")
@require_http_methods(["GET", "POST"])
def package_edit(request: HttpRequest, pk: int) -> HttpResponse:
    package = get_object_or_404(
        ServicePackage.objects.select_related("service"), pk=pk
    )

    if request.method == "POST":
        form = ServicePackageForm(request.POST, instance=package)
        if form.is_valid():
            try:
                services.save_catalog_object(form=form, actor=request.user)
                services.set_package_features(
                    package=package, actor=request.user,
                    included_ids=[int(value) for value in
                                  request.POST.getlist("features")
                                  if value.isdigit()],
                )
            except ValidationError as exc:
                for message in exc.messages:
                    form.add_error(None, message)
            else:
                messages.success(request, _("Package saved."))
                return redirect("staff:catalog_service", pk=package.service_id)
    else:
        form = ServicePackageForm(instance=package)

    included = set(
        package.package_features.filter(is_included=True)
        .values_list("feature_id", flat=True)
    )

    return render(request, "catalog/admin/package_form.html", _shell(
        f"{package.service.name} — {package.name}",
        "Which of the service's features this tier includes.",
        package=package, form=form,
        features=[
            {"feature": feature, "included": feature.pk in included}
            for feature in package.service.features.all().order_by("order", "pk")
        ],
        breadcrumbs=CATALOG_BREADCRUMB,
    ))


@require_permission("catalog_delete")
@require_http_methods(["POST"])
def package_delete(request: HttpRequest, pk: int) -> HttpResponse:
    package = get_object_or_404(ServicePackage, pk=pk)
    service_id = package.service_id
    services.delete_catalog_object(instance=package, actor=request.user)
    return redirect("staff:catalog_service", pk=service_id)


# --- add-ons -----------------------------------------------------------------


@require_permission("catalog_view")
def addon_list(request: HttpRequest) -> HttpResponse:
    return render(request, "catalog/admin/addon_list.html", _shell(
        "Add-ons", "Sold alongside a service, or on their own.",
        addons=ServiceAddon.objects.select_related("service").order_by("order", "name"),
        form=ServiceAddonForm(),
        columns=[{"label": "Add-on"}, {"label": "Applies to"},
                 {"label": "Price", "align": "right"}, {"label": "Status"},
                 {"label": "", "align": "right", "sr_label": "Actions"}],
        breadcrumbs=CATALOG_BREADCRUMB,
    ))


@require_permission("catalog_create")
@require_http_methods(["POST"])
def addon_create(request: HttpRequest) -> HttpResponse:
    form = ServiceAddonForm(request.POST)

    if form.is_valid():
        try:
            services.save_catalog_object(form=form, actor=request.user, created=True)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, _("Add-on created."))
    else:
        messages.error(request, _("That add-on could not be created."))

    return redirect("staff:catalog_addons")


@require_permission("catalog_delete")
@require_http_methods(["POST"])
def addon_delete(request: HttpRequest, pk: int) -> HttpResponse:
    addon = get_object_or_404(ServiceAddon, pk=pk)
    services.delete_catalog_object(instance=addon, actor=request.user)
    return redirect("staff:catalog_addons")
