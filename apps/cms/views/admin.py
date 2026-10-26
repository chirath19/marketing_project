"""The staff screens that edit website content.

Two generic views drive every collection, and three more handle pages and
their sections. Every one is guarded; `cms_view` opens a screen,
`cms_edit` / `cms_create` / `cms_delete` gate the writes, and `cms_publish`
is separate again — preparing a page and deciding it is ready are
different decisions.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.cms import selectors, services
from apps.cms.collections import COLLECTIONS, get_collection
from apps.cms.forms import (
    ContactSettingsForm,
    PageForm,
    PageSectionForm,
    SectionItemForm,
    SiteSettingsForm,
)
from apps.cms.models import Page, PageSection, SectionItem
from apps.cms.sections import SECTION_TYPES
from apps.permissions.guards import require_permission

CONTENT_BREADCRUMB = [{"label": "Website content", "href": "/staff/cms/"}]


def _shell(title: str, subtitle: str = "", **extra) -> dict:
    return {"page_title": title, "page_subtitle": subtitle,
            "nav_key": "cms", **extra}


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


@require_permission("cms_view")
def content_home(request: HttpRequest) -> HttpResponse:
    return render(request, "cms/admin/home.html", _shell(
        "Website content",
        "Pages, the shared lists they draw on, and the site's own details.",
        pages=Page.objects.prefetch_related("sections").order_by("kind", "title"),
        collections=COLLECTIONS,
        site=selectors.site_settings(),
    ))


# ---------------------------------------------------------------------------
# Site settings
# ---------------------------------------------------------------------------


@require_permission("cms_view")
@require_http_methods(["GET", "POST"])
def site_settings(request: HttpRequest) -> HttpResponse:
    instance = selectors.site_settings()

    if request.method == "POST":
        form = SiteSettingsForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            services.update_site_settings(form=form, actor=request.user)
            messages.success(request, _("Site details saved."))
            return redirect("staff:cms_settings")
    else:
        form = SiteSettingsForm(instance=instance)

    return render(request, "cms/admin/site_settings.html", _shell(
        "Site details",
        "Name, contact details and the defaults every page falls back to.",
        form=form, breadcrumbs=CONTENT_BREADCRUMB,
    ))


# ---------------------------------------------------------------------------
# Pages and their sections
# ---------------------------------------------------------------------------


@require_permission("cms_edit")
@require_http_methods(["GET", "POST"])
def contact_settings(request: HttpRequest) -> HttpResponse:
    form = ContactSettingsForm(
        request.POST if request.method == "POST" else None, instance=selectors.site_settings(),
    )
    if request.method == "POST" and form.is_valid():
        services.update_site_settings(form=form, actor=request.user)
        messages.success(request, _("Primary contact details saved."))
        return redirect("staff:cms_contacts")
    return render(request, "cms/admin/contacts.html", _shell(
        "Contact details", "Primary details appear on the Contact page and in the website footer.",
        form=form, breadcrumbs=CONTENT_BREADCRUMB,
    ))


@require_permission("cms_create")
@require_http_methods(["GET", "POST"])
def page_create(request: HttpRequest) -> HttpResponse:
    form = PageForm(request.POST if request.method == "POST" else None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            page = services.create_page(actor=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, _("Draft created. Add sections, then publish when ready."))
            return redirect("staff:cms_page", pk=page.pk)
    return render(request, "cms/admin/form.html", _shell(
        "Create a page", "Start with a draft. Add content before publishing it.",
        form=form, submit_label="Create draft page", back_url=reverse("staff:module_cms"),
        breadcrumbs=CONTENT_BREADCRUMB,
    ))


@require_permission("cms_view")
def page_detail(request: HttpRequest, pk: int) -> HttpResponse:
    page = get_object_or_404(
        Page.objects.prefetch_related("sections__items"), pk=pk
    )

    return render(request, "cms/admin/page_detail.html", _shell(
        page.title, f"/{page.slug}/",
        page=page,
        sections=page.sections.all().order_by("order", "pk"),
        section_types=SECTION_TYPES,
        breadcrumbs=CONTENT_BREADCRUMB,
    ))


@require_permission("cms_edit")
@require_http_methods(["GET", "POST"])
def page_edit(request: HttpRequest, pk: int) -> HttpResponse:
    page = get_object_or_404(Page, pk=pk)

    if request.method == "POST":
        form = PageForm(request.POST, request.FILES, instance=page)
        if form.is_valid():
            services.save_object(form=form, actor=request.user)
            messages.success(request, _("Page saved."))
            return redirect("staff:cms_page", pk=page.pk)
    else:
        form = PageForm(instance=page)

    return render(request, "cms/admin/form.html", _shell(
        f"Edit {page.title}", "Title, address and search engine details",
        form=form, back_url=f"/staff/cms/pages/{page.pk}/",
        breadcrumbs=CONTENT_BREADCRUMB,
    ))


@require_permission("cms_publish")
@require_http_methods(["POST"])
def page_publish(request: HttpRequest, pk: int) -> HttpResponse:
    page = get_object_or_404(Page, pk=pk)
    publish = request.POST.get("publish") == "1"

    if publish:
        services.publish_page(page=page, actor=request.user)
        messages.success(request, _("%(title)s is live.") % {"title": page.title})
    else:
        services.unpublish_page(page=page, actor=request.user)
        messages.success(request, _("%(title)s is back to draft.") % {
            "title": page.title})

    return redirect("staff:cms_page", pk=page.pk)


@require_permission("cms_create")
@require_http_methods(["GET", "POST"])
def section_create(request: HttpRequest, pk: int) -> HttpResponse:
    """Add a section, in two steps.

    The type is chosen first, because it decides which fields the form
    then shows. Presenting every field for every type and hoping the
    editor ignores the irrelevant ones is how sections end up half-filled.
    """
    page = get_object_or_404(Page, pk=pk)
    section_type = request.POST.get("section_type") or request.GET.get("type", "")

    if request.method == "POST" and request.POST.get("confirm") == "1":
        form = PageSectionForm(request.POST, request.FILES)
        if form.is_valid():
            form.instance.page = page
            services.save_object(form=form, actor=request.user, created=True)
            messages.success(request, _("Section added."))
            return redirect("staff:cms_page", pk=page.pk)
    else:
        form = PageSectionForm(initial={"section_type": section_type})

    return render(request, "cms/admin/section_form.html", _shell(
        f"Add a section to {page.title}",
        "Pick a type, then fill in what it needs.",
        page=page, form=form, section_type=section_type,
        section_types=SECTION_TYPES, creating=True,
        breadcrumbs=CONTENT_BREADCRUMB,
    ))


@require_permission("cms_edit")
@require_http_methods(["GET", "POST"])
def section_edit(request: HttpRequest, pk: int) -> HttpResponse:
    section = get_object_or_404(PageSection.objects.select_related("page"), pk=pk)

    if request.method == "POST":
        form = PageSectionForm(request.POST, request.FILES, instance=section)
        if form.is_valid():
            services.save_object(form=form, actor=request.user)
            messages.success(request, _("Section saved."))
            return redirect("staff:cms_page", pk=section.page_id)
    else:
        form = PageSectionForm(instance=section)

    return render(request, "cms/admin/section_form.html", _shell(
        f"Edit {section.get_section_type_display()}",
        f"On {section.page.title}",
        page=section.page, section=section, form=form,
        section_type=section.section_type, section_types=SECTION_TYPES,
        items=section.items.all().order_by("order", "pk"),
        item_form=SectionItemForm(section=section),
        breadcrumbs=CONTENT_BREADCRUMB,
    ))


@require_permission("cms_delete")
@require_http_methods(["POST"])
def section_delete(request: HttpRequest, pk: int) -> HttpResponse:
    section = get_object_or_404(PageSection, pk=pk)
    page_id = section.page_id
    services.delete_object(instance=section, actor=request.user)
    messages.success(request, _("Section removed."))
    return redirect("staff:cms_page", pk=page_id)


@require_permission("cms_edit")
@require_http_methods(["POST"])
def section_move(request: HttpRequest, pk: int) -> HttpResponse:
    section = get_object_or_404(PageSection, pk=pk)
    services.move(instance=section, actor=request.user,
                  direction=request.POST.get("direction", "up"))
    return redirect("staff:cms_page", pk=section.page_id)


@require_permission("cms_edit")
@require_http_methods(["POST"])
def section_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    section = get_object_or_404(PageSection, pk=pk)
    services.set_visibility(instance=section, actor=request.user,
                            visible=request.POST.get("visible") == "1")
    return redirect("staff:cms_page", pk=section.page_id)


# --- repeating items inside a section --------------------------------------


def _item_section(pk: int) -> PageSection:
    section = get_object_or_404(PageSection.objects.select_related("page"), pk=pk)
    if not section.type_config or not section.type_config.supports_items:
        raise Http404("This section does not contain repeating items.")
    return section


@require_permission("cms_create")
@require_http_methods(["GET", "POST"])
def item_create(request: HttpRequest, pk: int) -> HttpResponse:
    section = _item_section(pk)
    form = SectionItemForm(request.POST if request.method == "POST" else None, section=section)
    if request.method == "POST" and form.is_valid():
        form.instance.section = section
        services.save_object(form=form, actor=request.user, created=True)
        messages.success(request, _("Item added."))
        return redirect("staff:cms_section", pk=section.pk)
    return render(request, "cms/admin/form.html", _shell(
        f"Add {section.type_config.item_label.lower()}",
        f"On {section.page.title}: {section.heading}",
        form=form, submit_label="Add item",
        back_url=reverse("staff:cms_section", args=[section.pk]),
        breadcrumbs=CONTENT_BREADCRUMB,
    ))


@require_permission("cms_edit")
@require_http_methods(["GET", "POST"])
def item_edit(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(SectionItem.objects.select_related("section__page"), pk=pk)
    _item_section(item.section_id)
    form = SectionItemForm(request.POST if request.method == "POST" else None, instance=item)
    if request.method == "POST" and form.is_valid():
        services.save_object(form=form, actor=request.user)
        messages.success(request, _("Item saved."))
        return redirect("staff:cms_section", pk=item.section_id)
    return render(request, "cms/admin/form.html", _shell(
        f"Edit {item.section.type_config.item_label.lower()}", f"On {item.section.page.title}",
        form=form, back_url=reverse("staff:cms_section", args=[item.section_id]),
        breadcrumbs=CONTENT_BREADCRUMB,
    ))


@require_permission("cms_edit")
@require_http_methods(["POST"])
def item_move(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(SectionItem, pk=pk)
    services.move(instance=item, actor=request.user,
                  direction=request.POST.get("direction", "up"))
    return redirect("staff:cms_section", pk=item.section_id)


@require_permission("cms_edit")
@require_http_methods(["POST"])
def item_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(SectionItem, pk=pk)
    services.set_visibility(instance=item, actor=request.user,
                            visible=request.POST.get("visible") == "1")
    return redirect("staff:cms_section", pk=item.section_id)


@require_permission("cms_delete")
@require_http_methods(["POST"])
def item_delete(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(SectionItem, pk=pk)
    section_id = item.section_id
    services.delete_object(instance=item, actor=request.user)
    return redirect("staff:cms_section", pk=section_id)


# ---------------------------------------------------------------------------
# The shared collections — one pair of views for all of them
# ---------------------------------------------------------------------------


def _collection_or_404(key: str):  # noqa: ANN202
    collection = get_collection(key)
    if collection is None:
        raise Http404("No such collection.")
    return collection


@require_permission("cms_view")
def collection_list(request: HttpRequest, key: str) -> HttpResponse:
    collection = _collection_or_404(key)

    rows = collection.model.objects.all().order_by("order", "pk")
    if collection.select_related:
        rows = rows.select_related(*collection.select_related)

    return render(request, "cms/admin/collection_list.html", _shell(
        collection.label, collection.description,
        collection=collection, rows=rows,
        columns=[{"label": heading} for heading, _attr in collection.columns]
        + [{"label": "Visible"}, {"label": "", "align": "right",
                                  "sr_label": "Actions"}],
        breadcrumbs=CONTENT_BREADCRUMB,
    ))


@require_permission("cms_view")
@require_http_methods(["GET", "POST"])
def collection_edit(request: HttpRequest, key: str, pk: int = 0) -> HttpResponse:
    """Create or edit one row of a collection.

    `cms_view` opens the form; the service then requires `cms_create` or
    `cms_edit` depending on whether the row is new, so a viewer can look
    at the form but not save it.
    """
    collection = _collection_or_404(key)
    instance = get_object_or_404(collection.model, pk=pk) if pk else None

    if request.method == "POST":
        form = collection.form(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            try:
                services.save_object(form=form, actor=request.user,
                                     created=instance is None)
            except PermissionDenied:
                raise
            except ValidationError as exc:
                for message in exc.messages:
                    form.add_error(None, message)
            else:
                messages.success(request, _("Saved."))
                return redirect("staff:cms_collection", key=key)
    else:
        form = collection.form(instance=instance)

    verb = "Edit" if instance else "Add"
    return render(request, "cms/admin/form.html", _shell(
        f"{verb} {collection.singular}", collection.description,
        form=form, back_url=f"/staff/cms/{key}/", collection=collection,
        breadcrumbs=CONTENT_BREADCRUMB,
    ))


@require_permission("cms_delete")
@require_http_methods(["POST"])
def collection_delete(request: HttpRequest, key: str, pk: int) -> HttpResponse:
    collection = _collection_or_404(key)
    instance = get_object_or_404(collection.model, pk=pk)
    services.delete_object(instance=instance, actor=request.user)
    messages.success(request, _("Deleted."))
    return redirect("staff:cms_collection", key=key)


@require_permission("cms_edit")
@require_http_methods(["POST"])
def collection_move(request: HttpRequest, key: str, pk: int) -> HttpResponse:
    collection = _collection_or_404(key)
    instance = get_object_or_404(collection.model, pk=pk)
    services.move(instance=instance, actor=request.user,
                  direction=request.POST.get("direction", "up"))
    return redirect("staff:cms_collection", key=key)


@require_permission("cms_edit")
@require_http_methods(["POST"])
def collection_toggle(request: HttpRequest, key: str, pk: int) -> HttpResponse:
    collection = _collection_or_404(key)
    instance = get_object_or_404(collection.model, pk=pk)
    services.set_visibility(instance=instance, actor=request.user,
                            visible=request.POST.get("visible") == "1")
    return redirect("staff:cms_collection", key=key)
