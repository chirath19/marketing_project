"""Site chrome for every template.

Navigation, social links and the site settings row come from the database
so they are editable, and are resolved lazily so pages that never mention
them — the API, the health check — pay nothing.
"""

from django.http import HttpRequest
from django.utils.functional import SimpleLazyObject

from apps.cms import selectors
from apps.cms.models import NavPlacement


def site_chrome(request: HttpRequest) -> dict:
    return {
        "site": SimpleLazyObject(selectors.site_settings),
        "header_nav": SimpleLazyObject(
            lambda: selectors.navigation(NavPlacement.HEADER)),
        "footer_nav_primary": SimpleLazyObject(
            lambda: selectors.navigation(NavPlacement.FOOTER_PRIMARY)),
        "footer_nav_secondary": SimpleLazyObject(
            lambda: selectors.navigation(NavPlacement.FOOTER_SECONDARY)),
        "footer_nav_legal": SimpleLazyObject(
            lambda: selectors.navigation(NavPlacement.LEGAL)),
        "contact_points": SimpleLazyObject(selectors.visible_contacts),
        "social_links": SimpleLazyObject(selectors.visible_social_links),
    }
