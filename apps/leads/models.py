"""Enquiries, quote requests and the leads they become.

Nothing here sends anything. Every submission is written to PostgreSQL
and surfaced in the staff Inbox; that is the whole delivery mechanism in
this version, by design.

Two records, deliberately separate:

* **ContactSubmission** — what someone actually sent, exactly as sent,
  kept unedited. It is evidence.
* **Lead** — the agency's working record about a person or company:
  status, owner, notes. Staff change this one.

A submission attaches to a lead, and a second enquiry from the same
address attaches to the same lead rather than starting a new one.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.organizations.models import Organization


class LeadStatus(models.TextChoices):
    NEW = "new", _("New")
    CONTACTED = "contacted", _("Contacted")
    QUALIFIED = "qualified", _("Qualified")
    PROPOSAL = "proposal", _("Proposal sent")
    WON = "won", _("Won")
    LOST = "lost", _("Lost")
    ARCHIVED = "archived", _("Archived")


#: Statuses that still need someone to do something.
OPEN_STATUSES = frozenset(
    {
        LeadStatus.NEW,
        LeadStatus.CONTACTED,
        LeadStatus.QUALIFIED,
        LeadStatus.PROPOSAL,
    }
)

#: Statuses that are finished. Kept, never deleted.
CLOSED_STATUSES = frozenset({LeadStatus.WON, LeadStatus.LOST, LeadStatus.ARCHIVED})


class SubmissionKind(models.TextChoices):
    CONTACT = "contact", _("Enquiry")
    QUOTE_REQUEST = "quote_request", _("Quote request")


class LeadSource(models.TextChoices):
    """Where an enquiry came from.

    Free-form would be more flexible and far less useful: "where do leads
    come from" is a question nobody can answer from a column of typos.
    """

    CONTACT_FORM = "contact_form", _("Contact form")
    QUOTE_BUILDER = "quote_builder", _("Quote builder")
    SERVICE_PAGE = "service_page", _("Service page")
    REFERRAL = "referral", _("Referral")
    PHONE = "phone", _("Phone")
    EVENT = "event", _("Event")
    OTHER = "other", _("Other")


class LeadQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status__in=OPEN_STATUSES)

    def unassigned(self):
        return self.open().filter(assigned_to__isnull=True)

    def for_listing(self):
        return self.select_related("assigned_to", "organization").order_by(
            "-last_activity_at", "-pk"
        )

    def readable_by(self, user):  # noqa: ANN001
        """Leads an actor may see.

        Deliberately **not** called `visible_to`: that name belongs to the
        tenant isolation rule, and this is a different rule. A lead has no
        client organization until it becomes one, so there is nothing to
        scope it to. Staff with the permission see the pipeline; a client
        sees nothing at all — their own enquiry is not a record they are
        entitled to browse.
        """
        from apps.leads import policies

        if not policies.can_view_leads(user):
            return self.none()
        return self


class Lead(TimeStampedModel):
    """The agency's working record about a prospect."""

    name = models.CharField(_("name"), max_length=150)
    company = models.CharField(_("company"), max_length=200, blank=True)
    email = models.EmailField(_("email"), max_length=254, db_index=True)
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    website = models.URLField(_("website"), max_length=300, blank=True)

    source = models.CharField(
        _("source"),
        max_length=30,
        choices=LeadSource.choices,
        default=LeadSource.CONTACT_FORM,
        db_index=True,
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=LeadStatus.choices,
        default=LeadStatus.NEW,
        db_index=True,
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_leads",
        verbose_name=_("assigned to"),
        help_text=_("Kept if the account is later closed, so the history still says who owned it."),
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
        verbose_name=_("client organization"),
        help_text=_(
            "Set once the lead becomes a client. Empty until then — "
            "an enquiry predates any client relationship."
        ),
    )

    estimated_value = models.DecimalField(
        _("estimated value"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("What this is worth per month, if known."),
    )

    last_activity_at = models.DateTimeField(_("last activity"), default=timezone.now, db_index=True)
    closed_at = models.DateTimeField(_("closed"), null=True, blank=True)

    objects = LeadQuerySet.as_manager()

    class Meta:
        verbose_name = _("lead")
        verbose_name_plural = _("leads")
        ordering = ["-last_activity_at", "-pk"]
        indexes = [
            models.Index(fields=["status", "-last_activity_at"], name="lead_status_activity_idx"),
            models.Index(fields=["assigned_to", "status"], name="lead_owner_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name}{f' · {self.company}' if self.company else ''}"

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("staff:lead_detail", kwargs={"pk": self.pk})

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def is_unassigned(self) -> bool:
        return self.assigned_to_id is None and self.is_open


class ContactSubmissionQuerySet(models.QuerySet):
    def genuine(self):
        """Everything not flagged as spam.

        Spam is kept rather than discarded, so a false positive can be
        found and rescued instead of silently losing somebody a client.
        """
        return self.filter(is_spam=False)

    def unread(self):
        return self.genuine().filter(read_at__isnull=True, is_archived=False)

    def inbox(self):
        return self.genuine().filter(is_archived=False)

    def for_listing(self):
        return self.select_related("lead", "lead__assigned_to", "read_by").order_by(
            "-created_at", "-pk"
        )


class ContactSubmission(TimeStampedModel):
    """What somebody actually sent.

    Never edited. Staff work on the `Lead`; this row stays as submitted,
    because it is the record of what was said and when.
    """

    kind = models.CharField(
        _("kind"),
        max_length=20,
        choices=SubmissionKind.choices,
        default=SubmissionKind.CONTACT,
        db_index=True,
    )

    name = models.CharField(_("name"), max_length=150)
    company = models.CharField(_("company"), max_length=200, blank=True)
    email = models.EmailField(_("email"), max_length=254)
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    website = models.URLField(_("website"), max_length=300, blank=True)
    subject = models.CharField(_("subject"), max_length=200, blank=True)
    message = models.TextField(_("message"))
    objective = models.CharField(
        _("main objective"),
        max_length=120,
        blank=True,
        help_text=_("What the enquirer chose as their main goal."),
    )
    budget_range = models.CharField(
        _("budget range"),
        max_length=60,
        blank=True,
        help_text=_(
            "Self-reported, and optional. A range the enquirer "
            "picked — not a figure anybody has agreed."
        ),
    )

    source = models.CharField(
        _("source"), max_length=30, choices=LeadSource.choices, default=LeadSource.CONTACT_FORM
    )
    page_url = models.CharField(
        _("page"),
        max_length=500,
        blank=True,
        help_text=_("Where on the site it was sent from."),
    )

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="submissions",
        null=True,
        blank=True,
        verbose_name=_("lead"),
    )

    # Inbox state.
    read_at = models.DateTimeField(_("read"), null=True, blank=True)
    read_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="read_submissions",
        verbose_name=_("read by"),
    )
    is_archived = models.BooleanField(_("archived"), default=False, db_index=True)

    # Spam handling.
    is_spam = models.BooleanField(_("flagged as spam"), default=False, db_index=True)
    spam_reason = models.CharField(_("why"), max_length=120, blank=True)

    # Provenance, for working out where a burst came from. The address is
    # hashed: this is a record of an enquiry, not a log of who browsed.
    ip_hash = models.CharField(_("address fingerprint"), max_length=64, blank=True)
    user_agent = models.CharField(_("browser"), max_length=300, blank=True)

    objects = ContactSubmissionQuerySet.as_manager()

    class Meta:
        verbose_name = _("contact submission")
        verbose_name_plural = _("contact submissions")
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(
                fields=["is_spam", "is_archived", "-created_at"], name="submission_inbox_idx"
            ),
            models.Index(fields=["read_at"], name="submission_read_idx"),
            models.Index(fields=["kind", "-created_at"], name="submission_kind_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} — {self.subject or self.get_kind_display()}"

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("staff:inbox_detail", kwargs={"pk": self.pk})

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    @property
    def preview(self) -> str:
        text = " ".join(self.message.split())
        return f"{text[:117]}…" if len(text) > 120 else text

    @property
    def display_subject(self) -> str:
        return self.subject or str(self.get_kind_display())


class QuoteItem(TimeStampedModel):
    """One service on a quote request.

    The name and price are **copied** at submission, not looked up later.
    A quote has to say what the visitor was shown; if the catalogue price
    changes next week, the request they sent must not silently change
    with it.
    """

    submission = models.ForeignKey(
        ContactSubmission,
        on_delete=models.CASCADE,
        related_name="quote_items",
        verbose_name=_("submission"),
    )

    service = models.ForeignKey(
        "catalog.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quote_items",
        verbose_name=_("service"),
    )
    package = models.ForeignKey(
        "catalog.ServicePackage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quote_items",
        verbose_name=_("package"),
    )

    name = models.CharField(_("what was selected"), max_length=250)
    price_display = models.CharField(_("price shown"), max_length=40, blank=True)
    billing_display = models.CharField(_("billing shown"), max_length=40, blank=True)
    order = models.PositiveIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("quote item")
        verbose_name_plural = _("quote items")
        ordering = ["order", "pk"]
        indexes = [
            models.Index(fields=["submission", "order"], name="quoteitem_order_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class ActivityKind(models.TextChoices):
    SUBMISSION = "submission", _("Enquiry received")
    NOTE = "note", _("Note")
    STATUS = "status", _("Status changed")
    ASSIGNMENT = "assignment", _("Assigned")
    CONVERTED = "converted", _("Converted to a client")


class LeadActivity(TimeStampedModel):
    """One entry on a lead's timeline.

    Append-only in practice: entries are written by the service layer and
    never edited, so the history of what happened stays trustworthy.
    """

    lead = models.ForeignKey(
        Lead, on_delete=models.CASCADE, related_name="activities", verbose_name=_("lead")
    )
    kind = models.CharField(
        _("kind"), max_length=20, choices=ActivityKind.choices, default=ActivityKind.NOTE
    )
    body = models.TextField(_("detail"), blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_activities",
        verbose_name=_("by"),
    )
    is_internal = models.BooleanField(
        _("internal"),
        default=True,
        help_text=_("Internal notes are staff only, in both directions."),
    )

    class Meta:
        verbose_name = _("lead activity")
        verbose_name_plural = _("lead activities")
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["lead", "-created_at"], name="activity_lead_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.lead}: {self.get_kind_display()}"


# ---------------------------------------------------------------------------
# Quote requests
#
# A third record, and deliberately not a fourth use of the first two.
#
# `ContactSubmission` is evidence of what somebody sent. `Lead` is the
# relationship with a person or company — one per email address, reopened
# when they come back, long-lived. A **quote request is one specific ask**,
# and the same client can have three of them open at once at three
# different stages. Folding them into the lead would make "which quote did
# they accept?" a question nobody could answer.
# ---------------------------------------------------------------------------


class QuoteStatus(models.TextChoices):
    NEW = "new", _("New")
    REVIEWING = "reviewing", _("Reviewing")
    CLARIFICATION_REQUIRED = "clarification_required", _("Clarification needed")
    PROPOSAL_READY = "proposal_ready", _("Proposal ready")
    ACCEPTED = "accepted", _("Accepted")
    DECLINED = "declined", _("Declined")
    CLOSED = "closed", _("Closed")


#: Quotes still waiting on somebody.
OPEN_QUOTE_STATUSES = frozenset(
    {
        QuoteStatus.NEW,
        QuoteStatus.REVIEWING,
        QuoteStatus.CLARIFICATION_REQUIRED,
        QuoteStatus.PROPOSAL_READY,
    }
)

#: Statuses a client is shown as a decision rather than as work in progress.
SETTLED_QUOTE_STATUSES = frozenset(
    {
        QuoteStatus.ACCEPTED,
        QuoteStatus.DECLINED,
        QuoteStatus.CLOSED,
    }
)


class QuoteRequestQuerySet(models.QuerySet):
    def for_listing(self) -> models.QuerySet:
        return self.select_related(
            "assigned_to", "organization", "lead", "submission"
        ).prefetch_related("items")

    def open(self) -> models.QuerySet:
        return self.filter(status__in=OPEN_QUOTE_STATUSES)

    def readable_by(self, user) -> models.QuerySet:  # noqa: ANN001
        """Rows this actor may see.

        Deliberately **not** called `visible_to`: that name belongs to
        the tenant isolation rule in `OrganizationOwnedQuerySet`, which
        has exactly one implementation, and this is a different rule.

        It is different because a quote request can arrive from somebody
        with no organization at all — which the tenancy base forbids by
        design — so the rule is spelled out here, and it has two halves
        rather than one.

        Staff see every quote, subject to the permission check in
        `policies`. A client sees quotes belonging to an organization they
        actively belong to, **and** quotes they personally submitted —
        the second half matters because a visitor can send a quote
        request before an organization exists for them, and should not
        lose sight of it the moment they register.
        """
        from apps.organizations.models import ACTIVE_MEMBERSHIP_STATUSES

        if not user or not getattr(user, "is_authenticated", False):
            return self.none()

        if user.is_staff_member:
            return self

        return self.filter(
            models.Q(submitted_by=user, organization__isnull=True)
            | (
                (models.Q(submitted_by=user) | models.Q(submitted_by__isnull=True))
                & models.Q(organization__status="active")
                & models.Q(organization__memberships__user=user)
                & models.Q(organization__memberships__status__in=ACTIVE_MEMBERSHIP_STATUSES)
            )
        ).distinct()


class QuoteRequest(TimeStampedModel):
    """One request to be priced, and everything that happened to it."""

    reference = models.CharField(
        _("reference"),
        max_length=20,
        unique=True,
        db_index=True,
        help_text=_("What everyone calls this quote: on the phone, in a proposal, in an invoice."),
    )

    #: The submission that produced it. Evidence, never edited — the
    #: working copy of every field below lives on this row instead.
    submission = models.OneToOneField(
        ContactSubmission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quote_request",
        verbose_name=_("submission"),
    )
    lead = models.ForeignKey(
        Lead,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quote_requests",
        verbose_name=_("lead"),
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="quote_requests",
        verbose_name=_("client organization"),
        help_text=_(
            "Set when the request came from a signed-in client, or once staff attach it to one."
        ),
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quote_requests",
        verbose_name=_("submitted by"),
        help_text=_("The account that sent it, when the visitor was signed in."),
    )

    # --- who is asking ----------------------------------------------------
    # Copied rather than read through the lead: a quote has to say who it
    # was for even after the lead's details are corrected, and a year
    # later that difference is the whole point of keeping it.

    contact_name = models.CharField(_("name"), max_length=150)
    contact_email = models.EmailField(_("email"), max_length=254, db_index=True)
    contact_phone = models.CharField(_("phone"), max_length=32, blank=True)
    company_name = models.CharField(_("company"), max_length=200, blank=True)
    website = models.URLField(_("website"), max_length=300, blank=True)

    # --- what they asked for ----------------------------------------------

    objective = models.CharField(
        _("main objective"),
        max_length=120,
        blank=True,
        help_text=_("What they said success would look like."),
    )
    budget_range = models.CharField(
        _("budget range"),
        max_length=60,
        blank=True,
        help_text=_("Self-reported, and optional. Not a figure anybody has agreed."),
    )
    notes = models.TextField(
        _("what they told us"),
        blank=True,
        help_text=_("Their own words, as submitted."),
    )

    # --- working the request ----------------------------------------------

    status = models.CharField(
        _("status"),
        max_length=30,
        choices=QuoteStatus.choices,
        default=QuoteStatus.NEW,
        db_index=True,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_quote_requests",
        verbose_name=_("owner"),
    )
    staff_summary = models.TextField(
        _("scope summary"),
        blank=True,
        help_text=_(
            "What we are actually proposing. Shown to the client once the proposal is marked ready."
        ),
    )

    decided_at = models.DateTimeField(_("decided"), null=True, blank=True)
    closed_at = models.DateTimeField(_("closed"), null=True, blank=True)
    last_activity_at = models.DateTimeField(_("last activity"), default=timezone.now, db_index=True)

    objects = QuoteRequestQuerySet.as_manager()

    class Meta:
        verbose_name = _("quote request")
        verbose_name_plural = _("quote requests")
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="quote_status_created_idx"),
            models.Index(fields=["assigned_to", "status"], name="quote_owner_status_idx"),
            models.Index(fields=["organization", "-created_at"], name="quote_org_created_idx"),
            models.Index(fields=["contact_email"], name="quote_email_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.reference} — {self.contact_name}"

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("staff:quote_detail", kwargs={"pk": self.pk})

    def get_client_url(self) -> str:
        from django.urls import reverse

        return reverse("organizations:quote_detail", kwargs={"pk": self.pk})

    # --- derived -----------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_QUOTE_STATUSES

    @property
    def is_settled(self) -> bool:
        return self.status in SETTLED_QUOTE_STATUSES

    @property
    def is_active_work(self) -> bool:
        """Accepted and not yet closed: the agreed work is under way."""
        return self.status == QuoteStatus.ACCEPTED

    @property
    def lifecycle_label(self) -> str:
        """The status as people talk about it. An accepted quote is live work."""
        return str(_("Active")) if self.is_active_work else self.get_status_display()

    @property
    def included_items(self) -> list:
        """The lines currently in scope.

        A line staff removed is kept on the row and excluded here, so the
        record still shows what was asked for alongside what was quoted.
        """
        return [item for item in self.items.all() if item.is_included]

    @property
    def dropped_items(self) -> list:
        return [item for item in self.items.all() if not item.is_included]

    @property
    def client_visible_summary(self) -> str:
        """What the client is told about scope.

        Withheld until there is a proposal: a half-written scope note read
        by the client mid-draft causes exactly the conversation it was
        meant to prevent.
        """
        if self.status in {
            QuoteStatus.PROPOSAL_READY,
            QuoteStatus.ACCEPTED,
            QuoteStatus.DECLINED,
            QuoteStatus.CLOSED,
        }:
            return self.staff_summary
        return ""


class QuoteRequestItem(TimeStampedModel):
    """One line of a quote request.

    Seeded from the `QuoteItem` the visitor actually selected, and then
    editable — the submission keeps the record of what was asked for, so
    this copy is free to become what is being quoted.
    """

    quote = models.ForeignKey(
        QuoteRequest, on_delete=models.CASCADE, related_name="items", verbose_name=_("quote")
    )
    service = models.ForeignKey(
        "catalog.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quote_request_items",
        verbose_name=_("service"),
    )
    package = models.ForeignKey(
        "catalog.ServicePackage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quote_request_items",
        verbose_name=_("package"),
    )

    name = models.CharField(_("line"), max_length=250)
    #: What the visitor was shown at the moment they selected it. Never
    #: recalculated: the price on a request must not change because the
    #: catalogue did.
    price_display = models.CharField(_("price as shown"), max_length=40, blank=True)
    billing_display = models.CharField(_("billing as shown"), max_length=40, blank=True)

    #: What the agency is actually quoting, which may differ.
    quoted_amount = models.DecimalField(
        _("quoted amount"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Leave blank to quote this line on scope."),
    )
    currency = models.CharField(_("currency"), max_length=3, blank=True)
    billing_type = models.CharField(
        _("billing"),
        max_length=20,
        blank=True,
        help_text=_("one_time, monthly or custom."),
    )

    is_included = models.BooleanField(
        _("in scope"),
        default=True,
        help_text=_(
            "Turn off to drop a line from the proposal without erasing that it was asked for."
        ),
    )
    note = models.CharField(_("note"), max_length=250, blank=True)
    order = models.PositiveIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("quote line")
        verbose_name_plural = _("quote lines")
        ordering = ["order", "pk"]
        indexes = [
            models.Index(fields=["quote", "order"], name="quoteline_order_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class QuoteActivityKind(models.TextChoices):
    SUBMITTED = "submitted", _("Request received")
    NOTE = "note", _("Note")
    STATUS = "status", _("Status changed")
    ASSIGNMENT = "assignment", _("Assigned")
    SCOPE = "scope", _("Scope changed")
    CLIENT_MESSAGE = "client_message", _("From the client")


class QuoteActivity(TimeStampedModel):
    """One entry on a quote's timeline.

    `is_internal` is the whole reason this is not the lead timeline: a
    quote is the one workflow a client can see, so each entry has to
    declare whether they may read it. Internal is the default, because
    the safe mistake is a note the client does not see.
    """

    quote = models.ForeignKey(
        QuoteRequest, on_delete=models.CASCADE, related_name="activities", verbose_name=_("quote")
    )
    kind = models.CharField(
        _("kind"), max_length=20, choices=QuoteActivityKind.choices, default=QuoteActivityKind.NOTE
    )
    body = models.TextField(_("detail"), blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quote_activities",
        verbose_name=_("by"),
    )
    is_internal = models.BooleanField(
        _("internal"),
        default=True,
        help_text=_("Internal entries are never shown to the client."),
    )

    class Meta:
        verbose_name = _("quote activity")
        verbose_name_plural = _("quote activities")
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["quote", "-created_at"], name="quoteactivity_quote_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.quote.reference}: {self.get_kind_display()}"


class GuestQuoteAccess(TimeStampedModel):
    """Only a hash is retained; the private link is shown to its visitor once."""

    quote = models.OneToOneField(
        QuoteRequest, on_delete=models.CASCADE, related_name="guest_access"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
