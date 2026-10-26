"""Identity.

Two decisions shape this module.

**`status` is the only source of truth for whether an account may sign
in.** Django's `is_active` is kept as a derived, read-only property rather
than a second column, because two columns that must agree eventually
disagree — and the failure mode is a suspended account that can still log
in. `AbstractBaseUser` treats `is_active` as a plain attribute, so
overriding it with a property is well-supported; every query that needs
live accounts filters on `status` instead.

**There is no email verification**, because the platform sends nothing
outbound in this version. A self-registered client therefore lands in
`PENDING` and a staff member approves it from the dashboard. The approval
request is persisted and surfaced in the Inbox, which is where every
other inbound message goes too.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserType(models.TextChoices):
    SUPER_ADMIN = "super_admin", _("Super admin")
    STAFF = "staff", _("Staff")
    SYSTEM_OWNER = "system_owner", _("System Owner")
    CLIENT = "client", _("Client")


class AccountStatus(models.TextChoices):
    """The lifecycle of an account.

    PENDING   — registered, awaiting staff approval. Cannot sign in.
    ACTIVE    — approved. The only state that can sign in.
    SUSPENDED — temporarily blocked, expected to return (unpaid invoice,
                a security concern under investigation).
    DISABLED  — closed for good. Kept rather than deleted so that the
                leads, approvals and messages that reference it keep their
                history.
    """

    PENDING = "pending", _("Pending approval")
    ACTIVE = "active", _("Active")
    SUSPENDED = "suspended", _("Suspended")
    DISABLED = "disabled", _("Disabled")


#: The statuses a sign-in is permitted from. Deliberately a set of one:
#: anything new must opt in explicitly rather than inherit access.
SIGN_IN_ALLOWED_STATUSES = frozenset({AccountStatus.ACTIVE})


class UserQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=AccountStatus.ACTIVE)

    def pending(self):
        return self.filter(status=AccountStatus.PENDING)

    def clients(self):
        return self.filter(user_type=UserType.CLIENT)

    def staff_members(self):
        return self.filter(
            user_type__in=[UserType.STAFF, UserType.SUPER_ADMIN, UserType.SYSTEM_OWNER]
        )


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
    """Creates users with a normalised email as the login identifier."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("A user must have an email address.")
        email = self.normalize_email(email).lower().strip()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("user_type", UserType.CLIENT)
        extra.setdefault("status", AccountStatus.ACTIVE)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("user_type", UserType.SUPER_ADMIN)
        extra.setdefault("status", AccountStatus.ACTIVE)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)

        if extra.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        if extra.get("status") != AccountStatus.ACTIVE:
            raise ValueError("A superuser must be active.")

        return self._create_user(email, password, **extra)

    def get_by_natural_key(self, username: str | None):
        """Look up by email without regard to case.

        Addresses are stored lower-cased, so lower-casing the lookup term
        stays an exact, index-backed match. Doing this here rather than in
        the login form covers every authentication path — the sign-in
        page, the Django admin and the API alike.
        """
        return self.get(**{self.model.USERNAME_FIELD: (username or "").lower()})


class User(AbstractBaseUser, PermissionsMixin):
    """Platform user.

    `user_type` is the coarse division the brief describes. It decides
    which dashboard a session lands in; it is never the whole
    authorisation answer. Fine-grained rights come from the RBAC tables
    and object-level policies added in a later phase.
    """

    email = models.EmailField(_("email address"), unique=True, max_length=254)
    full_name = models.CharField(_("full name"), max_length=150, blank=True)
    user_type = models.CharField(
        _("user type"),
        max_length=20,
        choices=UserType.choices,
        default=UserType.CLIENT,
        db_index=True,
    )

    status = models.CharField(
        _("account status"),
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING,
        db_index=True,
        help_text=_("Only an active account can sign in."),
    )
    status_changed_at = models.DateTimeField(_("status changed at"), null=True, blank=True)
    status_reason = models.CharField(
        _("reason for current status"),
        max_length=255,
        blank=True,
        help_text=_("Shown to staff, never to the account holder."),
    )

    # Profile. Personal only. The company a user works for is an
    # Organization they are a member of — a company is never a column on a
    # user row, because a company has several people in it and the work
    # belongs to the company, not to whoever registered first.
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    job_title = models.CharField(_("job title"), max_length=120, blank=True)

    is_staff = models.BooleanField(
        _("Django admin access"),
        default=False,
        help_text=_(
            "Access to the Django admin. Distinct from the Staff user type, "
            "which grants access to the staff dashboard."
        ),
    )
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["email"]
        indexes = [
            models.Index(fields=["user_type", "status"], name="user_type_status_idx"),
            models.Index(fields=["status", "date_joined"], name="user_status_joined_idx"),
        ]

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        # Normalisation only — no business rules in save(). Status
        # transitions go through apps.accounts.services.
        self.email = self.email.lower().strip()
        super().save(*args, **kwargs)

    # --- Django's active flag, derived ---------------------------------

    @property
    def is_active(self) -> bool:
        """Whether Django should treat this account as usable.

        Read-only on purpose. Setting it would create a second source of
        truth; change `status` through the service layer instead, which
        records who changed it and why.
        """
        return self.status in SIGN_IN_ALLOWED_STATUSES

    # --- display -------------------------------------------------------

    def get_full_name(self) -> str:
        return self.full_name or self.email

    def get_short_name(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else self.email

    # --- roles ---------------------------------------------------------

    @property
    def is_super_admin(self) -> bool:
        return self.user_type == UserType.SUPER_ADMIN or self.is_superuser

    @property
    def is_staff_member(self) -> bool:
        return (
            self.user_type in {UserType.STAFF, UserType.SUPER_ADMIN, UserType.SYSTEM_OWNER}
            or self.is_superuser
        )

    @property
    def is_system_owner(self) -> bool:
        return self.user_type == UserType.SYSTEM_OWNER

    @property
    def is_client(self) -> bool:
        return self.user_type == UserType.CLIENT

    # --- status --------------------------------------------------------

    @property
    def is_pending_approval(self) -> bool:
        return self.status == AccountStatus.PENDING

    @property
    def can_sign_in(self) -> bool:
        return self.status in SIGN_IN_ALLOWED_STATUSES
