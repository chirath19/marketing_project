"""Client organizations and their members.

A client company is an `Organization`, never a `User`. One company has
many people in it — an owner, a marketing manager, someone in finance —
and the work the agency does belongs to the company, not to whoever
happened to fill in the registration form.

Everything the platform produces for a client (campaigns, subscriptions,
reports, approvals, messages) hangs off `Organization` through
`OrganizationOwnedModel` below. That base is what makes tenant isolation
a property of the data model rather than something each view has to
remember.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q, QuerySet
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class OrganizationStatus(models.TextChoices):
    """The lifecycle of a client company.

    PENDING   — created, not yet onboarded. Visible to staff only.
    ACTIVE    — live. Work can be delivered against it.
    SUSPENDED — temporarily stopped (unpaid invoice, a dispute).
    ARCHIVED  — the relationship has ended. Kept, never deleted, so the
                campaigns and reports that reference it keep their
                history.
    """

    PENDING = "pending", _("Pending onboarding")
    ACTIVE = "active", _("Active")
    SUSPENDED = "suspended", _("Suspended")
    ARCHIVED = "archived", _("Archived")


#: The statuses from which a client may use the platform. A set of one,
#: so anything new has to opt in rather than inherit access.
OPERATIONAL_STATUSES = frozenset({OrganizationStatus.ACTIVE})


class MemberRole(models.TextChoices):
    """What a person may do inside their own organization.

    OWNER   — everything, including billing and removing other members.
    ADMIN   — manages people and settings, approves work.
    MEMBER  — day-to-day use: sees campaigns and reports, approves work.
    VIEWER  — read-only. For a finance contact or an exec who only
              wants the numbers.
    """

    OWNER = "owner", _("Owner")
    ADMIN = "admin", _("Admin")
    MEMBER = "member", _("Member")
    VIEWER = "viewer", _("Viewer")


class MemberStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    SUSPENDED = "suspended", _("Suspended")
    REMOVED = "removed", _("Removed")


#: Only an active membership grants access.
ACTIVE_MEMBERSHIP_STATUSES = frozenset({MemberStatus.ACTIVE})

#: Roles that may change organization settings and manage people.
MANAGING_ROLES = frozenset({MemberRole.OWNER, MemberRole.ADMIN})


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------


class OrganizationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=OrganizationStatus.ACTIVE)

    def visible_to(self, user) -> QuerySet:  # noqa: ANN001
        """The organizations an actor may see.

        Staff see every client. A client sees only the organizations they
        hold an active membership in — and only while that organization
        is itself operational, so a suspended company does not keep a
        back door open through one of its users.
        """
        if not user or not getattr(user, "is_authenticated", False):
            return self.none()

        if user.is_staff_member:
            return self

        return self.filter(
            memberships__user=user,
            memberships__status__in=ACTIVE_MEMBERSHIP_STATUSES,
        ).distinct()


class Organization(TimeStampedModel):
    """A client company."""

    name = models.CharField(
        _("legal name"), max_length=200,
        help_text=_("The registered company name, used on quotes and invoices."),
    )
    display_name = models.CharField(
        _("display name"), max_length=200, blank=True,
        help_text=_("Trading name, if it differs. Shown in the dashboard."),
    )
    slug = models.SlugField(
        _("slug"), max_length=220, unique=True,
        help_text=_("Used in URLs. Stable: changing it breaks existing links."),
    )

    website = models.URLField(_("website"), max_length=255, blank=True)
    email = models.EmailField(
        _("general contact email"), max_length=254, blank=True,
        help_text=_("A record of where to reach the company. "
                    "The platform does not send to it."),
    )
    phone = models.CharField(_("phone"), max_length=32, blank=True)

    address_line1 = models.CharField(_("address line 1"), max_length=200, blank=True)
    address_line2 = models.CharField(_("address line 2"), max_length=200, blank=True)
    city = models.CharField(_("city"), max_length=120, blank=True)
    region = models.CharField(
        _("state or region"), max_length=120, blank=True,
        help_text=_("State, province or region, where one applies."),
    )
    postal_code = models.CharField(_("postal code"), max_length=24, blank=True)
    country = models.CharField(
        _("country"), max_length=100, blank=True,
        help_text=_("Free text for now. If a controlled list is wanted later, "
                    "this column holds the name and can take a code instead."),
    )

    status = models.CharField(
        _("status"), max_length=20, choices=OrganizationStatus.choices,
        default=OrganizationStatus.PENDING, db_index=True,
    )
    status_changed_at = models.DateTimeField(_("status changed at"), null=True, blank=True)

    notes = models.TextField(
        _("internal notes"), blank=True,
        help_text=_("Staff only. Never shown to the client."),
    )

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        verbose_name = _("organization")
        verbose_name_plural = _("organizations")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["status", "name"], name="org_status_name_idx"),
            models.Index(fields=["created_at"], name="org_created_idx"),
        ]

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        """What to show on screen."""
        return self.display_name or self.name

    @property
    def is_operational(self) -> bool:
        return self.status in OPERATIONAL_STATUSES

    @property
    def address_lines(self) -> list[str]:
        """The address as display lines, skipping the parts not filled in."""
        city_line = " ".join(filter(None, [self.city, self.postal_code])).strip()
        return [line for line in (
            self.address_line1, self.address_line2, city_line,
            self.region, self.country,
        ) if line]

    @staticmethod
    def build_slug(name: str, *, taken: set[str] | None = None) -> str:
        """A unique, URL-safe slug for a company name.

        Collisions are resolved with a numeric suffix rather than by
        raising: two clients genuinely can be called the same thing, and
        a registration should not fail because of it.
        """
        base = slugify(name)[:200] or "organization"
        taken = taken or set()

        candidate = base
        suffix = 2
        while candidate in taken:
            candidate = f"{base}-{suffix}"[:220]
            suffix += 1
        return candidate


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


class OrganizationMemberQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status__in=ACTIVE_MEMBERSHIP_STATUSES)

    def managers(self):
        return self.active().filter(role__in=MANAGING_ROLES)

    def visible_to(self, user) -> QuerySet:  # noqa: ANN001
        """Memberships an actor may see.

        A client sees the people in their own organizations and nobody
        else's — the core isolation rule, expressed once here rather than
        re-derived in every view.
        """
        if not user or not getattr(user, "is_authenticated", False):
            return self.none()

        if user.is_staff_member:
            return self

        return self.filter(
            organization__memberships__user=user,
            organization__memberships__status__in=ACTIVE_MEMBERSHIP_STATUSES,
        ).distinct()


class OrganizationMember(TimeStampedModel):
    """A person's place inside a client organization."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships",
        verbose_name=_("organization"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="organization_memberships", verbose_name=_("user"),
    )

    role = models.CharField(
        _("role"), max_length=20, choices=MemberRole.choices,
        default=MemberRole.MEMBER, db_index=True,
    )
    status = models.CharField(
        _("status"), max_length=20, choices=MemberStatus.choices,
        default=MemberStatus.ACTIVE, db_index=True,
    )
    job_title = models.CharField(
        _("job title in this organization"), max_length=120, blank=True,
        help_text=_("Overrides the title on the user's profile, if set."),
    )

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="organization_invitations_sent", verbose_name=_("added by"),
    )

    objects = OrganizationMemberQuerySet.as_manager()

    class Meta:
        verbose_name = _("organization member")
        verbose_name_plural = _("organization members")
        ordering = ["organization__name", "role", "user__email"]
        constraints = [
            # One person holds one place in a company. Two memberships
            # would mean two different answers to "what may they do here".
            models.UniqueConstraint(
                fields=["organization", "user"], name="unique_membership_per_org",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "status"], name="member_user_status_idx"),
            models.Index(fields=["organization", "status", "role"],
                         name="member_org_status_role_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user} in {self.organization} ({self.get_role_display()})"

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_MEMBERSHIP_STATUSES

    @property
    def can_manage(self) -> bool:
        return self.is_active and self.role in MANAGING_ROLES

    @property
    def is_owner(self) -> bool:
        return self.is_active and self.role == MemberRole.OWNER


# ---------------------------------------------------------------------------
# Tenancy base
# ---------------------------------------------------------------------------


class OrganizationOwnedQuerySet(models.QuerySet):
    """Scoping shared by every tenant-owned model."""

    def for_organization(self, organization) -> QuerySet:  # noqa: ANN001
        if organization is None:
            return self.none()
        return self.filter(organization=organization)

    def visible_to(self, user) -> QuerySet:  # noqa: ANN001
        """Rows the actor is allowed to see.

        Staff see everything; a client sees only rows belonging to an
        organization they actively belong to. This is the single
        implementation of the isolation rule — a domain that uses this
        base inherits it and cannot forget it.
        """
        if not user or not getattr(user, "is_authenticated", False):
            return self.none()

        if user.is_staff_member:
            return self

        return self.filter(
            Q(organization__memberships__user=user)
            & Q(organization__memberships__status__in=ACTIVE_MEMBERSHIP_STATUSES)
        ).distinct()


class OrganizationOwnedModel(models.Model):
    """Base for anything that belongs to a client organization.

    Campaigns, subscriptions, reports, approvals and messages all inherit
    from this, so none of them can exist without an owner and none of
    them needs its own isolation logic.

    `PROTECT` is deliberate: deleting a company that still has campaigns
    attached should fail loudly rather than quietly taking the history
    with it. Archive the organization instead.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="%(app_label)s_%(class)s_set",
        verbose_name=_("organization"), db_index=True,
    )

    objects = OrganizationOwnedQuerySet.as_manager()

    class Meta:
        abstract = True
