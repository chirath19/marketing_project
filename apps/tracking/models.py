"""The agency's own website analytics — deliberately not client analytics.

Everything in this app measures **this platform's own public site**:
who visits, what they look at, whether they request a quote. It is kept
in its own app, with its own models and its own admin page, so it can
never be confused with a client's Meta or Google performance — mixing
the two is the one thing section 2 of the brief is most insistent about,
and the cleanest way to guarantee it is for them to share no table.

Two concerns live here, and they are different concerns:

* **Tag configuration** (`TrackingSettings`) — which third-party tags
  the public site is allowed to load, and their IDs. This is
  configuration, not data: GTM, GA4, the Meta Pixel and RudderStack are
  all *optional*, consent-gated, and loaded client-side. Nothing here
  reads their numbers back.
* **Funnel events** (`AgencyWebsiteEvent`) — a real, first-party record
  of the taxonomy in `apps/tracking/events.py`, stored in this
  platform's own PostgreSQL. This is what the admin "Agency Website"
  analytics page reports on for the funnel metrics (quote starts,
  submissions, registrations); GA4's own visitor/session counts are a
  **separate, external** number this platform only ever displays if a
  GA4 connection has actually been configured in `apps.integrations` —
  see `apps/tracking/selectors.py`.
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class ConsentCategory(models.TextChoices):
    """The three categories a visitor consents to, independently.

    `NECESSARY` is not actually optional — the session and CSRF cookies
    this platform needs to function do not ask permission, the same way
    they do not anywhere else — but it is listed so the consent banner
    can say so explicitly rather than only listing what can be declined.
    """

    NECESSARY = "necessary", _("Necessary")
    ANALYTICS = "analytics", _("Analytics")
    ADVERTISING = "advertising", _("Advertising")


class TrackingSettingsManager(models.Manager):
    def current(self) -> TrackingSettings:
        """The one settings row, created on first use.

        The same singleton pattern `apps.cms.SiteSettings` already uses —
        a table that enforces exactly one row via `pk=1` rather than a
        bare key-value store, so every field keeps its own help text and
        validation. A seed migration creates this row on deploy, so in
        practice this is always a single `SELECT`; `self.create()` is
        only the fallback for a database that predates that migration.
        """
        obj = self.first()
        if obj is None:
            obj = self.create(pk=1)
        return obj


class TrackingSettings(models.Model):
    """Agency website tag configuration. Exactly one row.

    Every ID here is optional and blank by default: an unconfigured
    platform loads no third-party script at all, which is the correct
    and honest starting state rather than a placeholder ID that would
    silently send events nowhere useful.
    """

    gtm_container_id = models.CharField(
        _("GTM container ID"), max_length=20, blank=True,
        help_text=_("e.g. GTM-XXXXXXX. Manages which tags load — GTM "
                    "itself is not where analytics are read back from."),
    )
    ga4_measurement_id = models.CharField(
        _("GA4 measurement ID"), max_length=20, blank=True,
        help_text=_("e.g. G-XXXXXXXXXX. Loads GA4 tracking in the "
                    "visitor's browser. Reporting back into this "
                    "dashboard is a separate connection — see "
                    "Integrations → Google Analytics."),
    )
    meta_pixel_id = models.CharField(
        _("Meta Pixel ID"), max_length=30, blank=True,
        help_text=_("Reports website events to Meta for ad measurement "
                    "and targeting. It does not pull advertising results "
                    "back — that is the Meta Marketing API, configured "
                    "separately in Integrations."),
    )
    rudderstack_write_key = models.CharField(
        _("RudderStack write key"), max_length=100, blank=True,
    )
    rudderstack_data_plane_url = models.URLField(
        _("RudderStack data plane URL"), max_length=300, blank=True,
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    objects = TrackingSettingsManager()

    class Meta:
        verbose_name = _("tracking settings")
        verbose_name_plural = _("tracking settings")

    def __str__(self) -> str:
        return "Tracking settings"

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:  # noqa: ARG002
        raise ValidationError("The tracking settings row cannot be deleted.")

    @property
    def any_tag_configured(self) -> bool:
        return bool(self.gtm_container_id or self.ga4_measurement_id
                    or self.meta_pixel_id or self.rudderstack_write_key)


class AgencyWebsiteEventQuerySet(models.QuerySet):
    def between(self, start, end) -> models.QuerySet:  # noqa: ANN001
        return self.filter(occurred_at__date__gte=start, occurred_at__date__lte=end)

    def named(self, event_name: str) -> models.QuerySet:
        return self.filter(event_name=event_name)


class AgencyWebsiteEvent(TimeStampedModel):
    """One occurrence of a named event in the public-site funnel.

    First-party, real, and the only source the admin "Agency Website"
    analytics page's funnel numbers come from — see
    `apps/tracking/events.py` for the fixed taxonomy and
    `apps/tracking/views.py` for how one of these gets written.

    No cookie, no visitor ID, no IP address. `session_fingerprint` is a
    salted one-way hash of a short-lived, first-party, httponly cookie
    value — enough to avoid counting one reload as two visits within a
    session, not enough to identify or re-identify a person. The same
    shape as the hashed address already used for enquiry rate limiting
    in `apps.core.ratelimit`.
    """

    event_name = models.CharField(_("event"), max_length=40, db_index=True)
    occurred_at = models.DateTimeField(_("occurred"), auto_now_add=True,
                                       db_index=True)
    path = models.CharField(_("page"), max_length=500, blank=True)
    referrer = models.CharField(_("referrer"), max_length=500, blank=True)
    utm_source = models.CharField(_("UTM source"), max_length=100, blank=True)
    utm_medium = models.CharField(_("UTM medium"), max_length=100, blank=True)
    utm_campaign = models.CharField(_("UTM campaign"), max_length=150,
                                    blank=True)
    session_fingerprint = models.CharField(
        _("session fingerprint"), max_length=64, blank=True, db_index=True,
        help_text=_("A salted hash of a short-lived first-party cookie. "
                    "Not a visitor identity."),
    )
    #: Carries the one piece of context a given event needs — a service
    #: slug for `service_view`, a lead id for `contact_submit`. Kept
    #: small and optional rather than one column per event type.
    context = models.CharField(_("context"), max_length=200, blank=True)

    objects = AgencyWebsiteEventQuerySet.as_manager()

    class Meta:
        verbose_name = _("agency website event")
        verbose_name_plural = _("agency website events")
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["event_name", "-occurred_at"],
                         name="trackevent_name_date_idx"),
            models.Index(fields=["session_fingerprint", "-occurred_at"],
                         name="trackevent_session_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_name} at {self.occurred_at:%Y-%m-%d %H:%M}"


def fingerprint_session(raw_value: str) -> str:
    """One-way hash of a session cookie value, for `session_fingerprint`.

    The same construction as `apps.core.ratelimit.hash_key`: salted with
    `SECRET_KEY` so the hash cannot be reversed or correlated with
    anything outside this platform, and kept as a function rather than a
    model method so it has no dependency on a request or a database row.
    """
    salted = f"{settings.SECRET_KEY}:{raw_value}"
    return hashlib.sha256(salted.encode()).hexdigest()
