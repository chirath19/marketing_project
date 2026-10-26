"""Staff profiles and their client assignments.

Two separate questions are answered here, and keeping them separate is
the point of the whole phase:

* **what may this person do** — roles and permissions, in `apps.permissions`;
* **whose work may they do it to** — the assignments below.

An SEO specialist with `seo_edit` can edit SEO campaigns. The assignment
decides *whose* SEO campaigns. Neither alone is authorisation.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.organizations.models import Organization


class StaffProfile(TimeStampedModel):
    """The agency-side record for a staff user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="staff_profile", verbose_name=_("user"),
    )

    job_title = models.CharField(_("job title"), max_length=120, blank=True)
    department = models.CharField(_("department"), max_length=120, blank=True)

    roles = models.ManyToManyField(
        "permissions.Role", related_name="staff_profiles",
        verbose_name=_("roles"), blank=True,
    )

    has_all_client_access = models.BooleanField(
        _("access to every client"), default=False,
        help_text=_(
            "For people whose work genuinely spans the whole book — a head "
            "of delivery, an analyst building cross-client reports. Everyone "
            "else sees only the clients they are assigned to."
        ),
    )

    notes = models.TextField(_("internal notes"), blank=True)

    class Meta:
        verbose_name = _("staff profile")
        verbose_name_plural = _("staff profiles")
        ordering = ["user__email"]
        indexes = [
            models.Index(fields=["has_all_client_access"],
                         name="staff_all_access_idx"),
        ]

    def __str__(self) -> str:
        return self.user.get_full_name()

    @property
    def role_names(self) -> list[str]:
        return list(self.roles.values_list("name", flat=True))


class AssignmentRole(models.TextChoices):
    """What a staff member does for a particular client."""

    ACCOUNT_MANAGER = "account_manager", _("Account manager")
    STRATEGIST = "strategist", _("Strategist")
    SPECIALIST = "specialist", _("Specialist")
    ANALYST = "analyst", _("Analyst")
    SUPPORT = "support", _("Support")


class AssignmentStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    ENDED = "ended", _("Ended")


#: Only an active assignment grants access to a client's data.
ACCESS_GRANTING_STATUSES = frozenset({AssignmentStatus.ACTIVE})


class StaffClientAssignmentQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status__in=ACCESS_GRANTING_STATUSES)

    def for_staff(self, user):  # noqa: ANN001
        return self.filter(staff__user=user)


class StaffClientAssignment(TimeStampedModel):
    """A staff member's access to one client organization.

    This is the "AND access to the client" half of authorisation. Ending
    an assignment removes a staff member's reach into that client's data
    on their very next request, without touching their role.
    """

    staff = models.ForeignKey(
        StaffProfile, on_delete=models.CASCADE, related_name="assignments",
        verbose_name=_("staff member"),
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="staff_assignments",
        verbose_name=_("client organization"),
    )

    role = models.CharField(
        _("role on this account"), max_length=32,
        choices=AssignmentRole.choices, default=AssignmentRole.SPECIALIST,
        db_index=True,
    )
    status = models.CharField(
        _("status"), max_length=20, choices=AssignmentStatus.choices,
        default=AssignmentStatus.ACTIVE, db_index=True,
    )
    is_primary = models.BooleanField(
        _("primary contact"), default=False,
        help_text=_("The person this client is told to contact first."),
    )

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="client_assignments_made",
    )
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)

    objects = StaffClientAssignmentQuerySet.as_manager()

    class Meta:
        verbose_name = _("staff client assignment")
        verbose_name_plural = _("staff client assignments")
        ordering = ["organization__name", "role"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "organization"],
                name="unique_assignment_per_staff_and_client",
            ),
        ]
        indexes = [
            models.Index(fields=["staff", "status"], name="assign_staff_status_idx"),
            models.Index(fields=["organization", "status"],
                         name="assign_org_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.staff} → {self.organization} ({self.get_role_display()})"

    @property
    def is_active(self) -> bool:
        return self.status in ACCESS_GRANTING_STATUSES
