"""The public service catalogue.

Nothing on these pages is written in a template. Every card, price,
feature and category comes from the database, so the agency changes what
it sells without a deploy.
"""

from __future__ import annotations

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from django.views.decorators.vary import vary_on_headers

from apps.catalog import quote_selection, selectors
from apps.catalog.models import ServiceCategory


def _intro_sections():  # noqa: ANN201
    """The editable introduction shown above the catalogue grid.

    A CMS page of kind "services", so the agency can rewrite how it
    frames its own offering without a deploy. It carries the slug
    "services", which the catalogue route claims first — so the page is
    never reachable on its own and cannot compete with the catalogue for
    the same search result.

    Returns an empty list if nobody has made one. The catalogue is the
    point of the page; the introduction is an enhancement.
    """
    from apps.cms import selectors as cms_selectors

    page = cms_selectors.services_intro_page()
    return (page, list(page.sections.all())) if page else (None, [])


def _catalogue(
    request: HttpRequest,
    services,
    *,
    title: str,
    subtitle: str = "",
    eyebrow: str = "",
    active_category: str = "",
    meta_description: str = "",
    intro=None,
) -> HttpResponse:
    """The shared catalogue page.

    The index and a category view differ in which services they show and
    what the heading says, and in nothing else.
    """
    intro_page, intro_sections = intro if intro is not None else (None, [])

    return render(
        request,
        "public/catalog/index.html",
        {
            "page_title": title,
            "page_subtitle": subtitle,
            "eyebrow": eyebrow,
            "meta_description": meta_description or subtitle,
            "services": services,
            "categories": selectors.live_categories(),
            "active_category": active_category,
            "featured": selectors.featured_services() if not active_category else [],
            "global_addons": selectors.global_addons(),
            "intro_page": intro_page,
            "intro_sections": intro_sections,
        },
    )


def services_index(request: HttpRequest) -> HttpResponse:
    """The full catalogue, under an editable introduction.

    The heading and intro come from the CMS when an editor has written
    them, and fall back to wording that describes the page accurately
    rather than promising anything.
    """
    intro_page, intro_sections = _intro_sections()

    return _catalogue(
        request,
        selectors.live_services(),
        title=intro_page.title if intro_page else "Services",
        eyebrow="What we do",
        subtitle=""
        if intro_sections
        else (
            "Every service is scoped and priced on its own. Take one, or "
            "combine several into a single programme."
        ),
        meta_description=(
            intro_page.meta_description
            if intro_page and intro_page.meta_description
            else "SEO, paid advertising, social media, email marketing, analytics "
            "and strategy — scoped and priced individually."
        ),
        intro=(intro_page, intro_sections),
    )


def services_category(request: HttpRequest, slug: str) -> HttpResponse:
    category = get_object_or_404(ServiceCategory.objects.visible(), slug=slug)

    return _catalogue(
        request,
        selectors.services_in_category(slug),
        title=category.name,
        eyebrow="Services",
        subtitle=category.short_description,
        meta_description=category.short_description or f"{category.name} services.",
        active_category=slug,
    )


def service_detail(request: HttpRequest, slug: str) -> HttpResponse:
    service = selectors.live_service(slug)
    if service is None:
        raise Http404("No such service.")

    return render(
        request,
        "public/catalog/detail.html",
        {
            "service": service,
            "related": selectors.related_services(service),
            "comparison": selectors.comparison_for(service),
            "packages": service.packages.visible().order_by("order", "pk"),
            "features": service.features.visible().order_by("order", "pk"),
            "addons": service.addons.all(),
            "faqs": service.faqs.visible().order_by("order", "pk"),
            "meta_title": service.resolved_meta_title(),
            "meta_description": service.resolved_meta_description(),
        },
    )


# ---------------------------------------------------------------------------
# Quote selection
#
# POST only. Adding something to a quote changes state, so it must not be
# reachable by a link a crawler or a prefetch can follow.
# ---------------------------------------------------------------------------


@require_http_methods(["POST"])
def quote_add(request: HttpRequest) -> HttpResponse:
    service_id = request.POST.get("service")
    package_id = request.POST.get("package") or None

    if not (service_id or "").isdigit():
        raise Http404

    service = selectors.live_services().filter(pk=int(service_id), can_request_quote=True).first()
    if service is None:
        # Not available for quotes, retired, or never existed. The same
        # answer for all three: a visitor learns nothing about what was
        # withdrawn.
        raise Http404

    if package_id:
        if not package_id.isdigit():
            raise Http404
        if not service.packages.visible().filter(pk=int(package_id)).exists():
            raise Http404
        package_id = int(package_id)
    else:
        package_id = None

    previous = quote_selection.selection_state(request)
    success = quote_selection.add(request, service.pk, package_id)
    if success:
        unchanged = previous == quote_selection.selection_state(request)
        message = (
            _("%(name)s is already in your quote.")
            if unchanged
            else _("%(name)s added to your quote.")
        ) % {"name": service.name}
    else:
        message = _(
            "Your quote already has as many services as we can take at once. "
            "Send it through and we will pick the rest up from there."
        )

    if request.headers.get("Accept") == "application/json":
        return JsonResponse(
            {
                "selection": quote_selection.selection_state(request),
                "count": quote_selection.count(request),
                "message": message,
            },
            status=200 if success else 409,
        )

    (messages.success if success else messages.error)(request, message)
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)

    return redirect("public:quote")


@require_http_methods(["POST"])
def quote_remove(request: HttpRequest) -> HttpResponse:
    quote_selection.remove(request, request.POST.get("key", ""))
    messages.success(request, _("Removed."))
    return redirect("public:quote")


@require_http_methods(["POST"])
def quote_clear(request: HttpRequest) -> HttpResponse:
    quote_selection.clear(request)
    return redirect("public:services")


@vary_on_headers("Accept")
def quote_review(request: HttpRequest) -> HttpResponse:
    """The selection, with what it adds up to and how to send it."""
    from apps.cms import selectors as cms_selectors

    lines = quote_selection.lines(request)
    if request.headers.get("Accept") == "application/json":
        response = JsonResponse(
            {
                "selection": quote_selection.selection_state(request),
                "count": len(lines),
            }
        )
        response["Cache-Control"] = "no-store"
        return response
    if request.user.is_authenticated and request.user.is_client:
        return redirect("organizations:quote_create")
    if request.operating.require_quote_account and request.GET.get("guest") != "1":
        return redirect("organizations:quote_create")
    totals = quote_selection.totals(lines)
    site = cms_selectors.site_settings()

    from apps.catalog.pricing import price_visible

    summary = "\n".join(
        (
            f"- {line.name} ({line.priced.price_display} {line.priced.billing_display})"
            if price_visible(line.priced, request.operating)
            else f"- {line.name}"
        )
        for line in lines
    )

    # A form carried over from a failed submission keeps its errors and
    # the visitor's typing; otherwise a fresh one, which also generates
    # the honeypot's signed timestamp.
    from apps.leads.forms import QuoteRequestForm

    quote_form = getattr(request, "quote_form", None) or QuoteRequestForm()

    return render(
        request,
        "public/catalog/quote.html",
        {
            "quote_form": quote_form,
            "show_quote_prices": any(
                price_visible(line.priced, request.operating) for line in lines
            ),
            "show_quote_totals": bool(lines)
            and all(price_visible(line.priced, request.operating) for line in lines),
            "lines": lines,
            "totals": totals,
            "summary": summary,
            "site": site,
            "mailto": _mailto(site, summary),
            "whatsapp": _whatsapp(site, summary),
        },
    )


def _request_body(summary: str) -> str:
    return (
        "I would like a quote for the following:\n\n"
        f"{summary}\n\n"
        "My name:\nCompany:\nWebsite:\nWhat we want to achieve:\n"
    )


def _mailto(site, summary: str) -> str:  # noqa: ANN001
    """A pre-filled email, opened in the visitor's own client.

    The platform sends nothing itself — the same rule as everywhere else
    in this version — so the selection travels in a mailto the visitor
    sends from their own address.
    """
    from urllib.parse import quote

    if not site.contact_email or not summary:
        return ""

    subject = quote("Quote request")
    body = quote(_request_body(summary))
    return f"mailto:{site.contact_email}?subject={subject}&body={body}"


def _whatsapp(site, summary: str) -> str:  # noqa: ANN001
    from urllib.parse import quote

    digits = "".join(c for c in site.whatsapp_number if c.isdigit())
    if not digits or not summary:
        return ""

    return f"https://wa.me/{digits}?text={quote(_request_body(summary))}"
