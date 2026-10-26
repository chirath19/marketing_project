"""Roles, role permissions and per-user overrides.

The granular rights themselves are `django.contrib.auth.Permission` rows,
generated from `catalogue.py`. This module adds the three things Django
does not give us:

* a **Role** — a named bundle of permissions, which is what staff are
  actually assigned;
* an explicit **RolePermission** join, so a grant can carry who made it
  and when;
* a **UserPermissionOverride**, which can *deny* as well as grant.

Deny is the reason the resolution runs through a custom backend rather
than Django's default. Django's permission check is a union across
backends — anything that grants wins — so a deny expressed in Django's own
tables would be unenforceable.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import Permission
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Role(TimeStampedModel):
    """A named bundle of permissions, assigned to staff.

    Deliberately not `auth.Group`. A Group's permissions are resolved by
    Django's own backend, which has no concept of a deny override and no
    concept of client scoping — so a Group would quietly grant rights
    that this platform's rules say should be refused.
    """

    name = models.CharField(_("name"), max_length=120, unique=True)
    slug = models.SlugField(_("slug"), max_length=140, unique=True)
    description = models.TextField(_("description"), blank=True)

    is_system = models.BooleanField(
        _("system role"), default=False,
        help_text=_("Shipped with the platform. Can be edited but not deleted."),
    )

    permissions = models.ManyToManyField(
        Permission, through="RolePermission", related_name="platform_roles",
        verbose_name=_("permissions"), blank=True,
    )

    class Meta:
        verbose_name = _("role")
        verbose_name_plural = _("roles")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)

    @property
    def permission_codenames(self) -> set[str]:
        return set(self.permissions.values_list("codename", flat=True))


class RolePermission(TimeStampedModel):
    """One permission granted to one role.

    An explicit through model rather than a plain M2M so a grant can be
    attributed — "who gave this role the ability to approve spend, and
    when" is an audit question that gets asked.
    """

    role = models.ForeignKey(Role, on_delete=models.CASCADE,
                             related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE,
                                   related_name="role_grants")
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="role_permissions_granted",
    )

    class Meta:
        verbose_name = _("role permission")
        verbose_name_plural = _("role permissions")
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"],
                                    name="unique_permission_per_role"),
        ]
        indexes = [
            models.Index(fields=["role", "permission"], name="roleperm_lookup_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.role} → {self.permission.codename}"


class OverrideEffect(models.TextChoices):
    GRANT = "grant", _("Grant")
    DENY = "deny", _("Deny")


class UserPermissionOverride(TimeStampedModel):
    """A permission granted to, or withheld from, one staff member.

    For the cases a role cannot express: one analyst who may also export,
    one specialist temporarily barred from approving spend while an
    incident is investigated.

    **Deny beats everything**, including a grant override and every role.
    A withheld permission that something else can re-grant is not a
    control at all.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="permission_overrides",
    )
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE,
                                   related_name="user_overrides")
    effect = models.CharField(
        _("effect"), max_length=10, choices=OverrideEffect.choices,
        default=OverrideEffect.GRANT, db_index=True,
    )
    reason = models.CharField(
        _("reason"), max_length=255, blank=True,
        help_text=_("Why this exception exists. Shown to staff only."),
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="permission_overrides_granted",
    )

    class Meta:
        verbose_name = _("permission override")
        verbose_name_plural = _("permission overrides")
        ordering = ["user__email", "permission__codename"]
        constraints = [
            # One answer per person per permission. Two rows would mean a
            # grant and a deny could both be true.
            models.UniqueConstraint(fields=["user", "permission"],
                                    name="unique_override_per_user_permission"),
        ]
        indexes = [
            models.Index(fields=["user", "effect"], name="override_user_effect_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user} {self.effect}s {self.permission.codename}"
