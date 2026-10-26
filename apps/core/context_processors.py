"""Template context available on every page."""

import logging

from django.conf import settings
from django.db import OperationalError, ProgrammingError
from django.http import HttpRequest
from django.utils.functional import SimpleLazyObject

from apps.core.operations import current

logger = logging.getLogger(__name__)


def _brand() -> dict:
    """Brand values, from the database so the agency can change them.

    Falls back to the settings defaults when the CMS row does not exist
    yet — a fresh database, or a management command running before the
    first migration has seeded it. The template contract is the same
    either way.
    """
    name = settings.SITE_NAME
    tagline = settings.SITE_TAGLINE
    contact_email = settings.SITE_CONTACT_EMAIL

    try:
        from apps.cms.selectors import site_settings

        site = site_settings()
    except (ProgrammingError, OperationalError):
        # The table does not exist yet: a fresh database, or a management
        # command running before `migrate`. Narrow on purpose — a real
        # database fault should surface, not be swallowed into defaults.
        logger.debug("Site settings unavailable; using settings defaults.")
    else:
        name = site.site_name or name
        tagline = site.tagline or tagline
        contact_email = site.contact_email or contact_email

    return {
        "name": name,
        "tagline": tagline,
        "contact_email": contact_email,
        "currency": settings.SITE_DEFAULT_CURRENCY,
        "theme_color": settings.SITE_THEME_COLOR,
    }


def site(request: HttpRequest) -> dict:
    """Brand and site-wide values.

    Namespaced deliberately. Flat names such as `site_name` collide with
    context that Django's own views supply — `LoginView`, for one, sets
    `site_name` from the request host, which silently replaced the brand
    name on the sign-in page. A nested dict cannot be clobbered that way.

    Lazy, so a request that never renders a template costs no query.
    """

    def features():
        from apps.core.features import FEATURES, visible

        operating = getattr(request, "operating", None)
        return {
            key: visible(key, getattr(request, "user", None), operating=operating)
            for key in FEATURES
        }

    return {
        "features": SimpleLazyObject(features),
        "brand": SimpleLazyObject(_brand),
        "debug": settings.DEBUG,
        "operating": getattr(request, "operating", SimpleLazyObject(current)),
    }
