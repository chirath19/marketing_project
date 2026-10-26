"""Create a superuser and one active example client, idempotently.

Intended for first-run setup on a fresh environment (local or Railway).
Goes through the normal service layer — `register_client` and
`approve_account`/`activate_organization` — rather than the ORM directly,
so the created rows are indistinguishable from a real signup that a
staff member approved.

Safe to run more than once: existing accounts are left as-is (password
not reset) and only reported back.
"""

from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import AccountStatus
from apps.accounts.services import RegistrationError, approve_account, register_client
from apps.organizations.models import OrganizationStatus
from apps.organizations.services import activate_organization

User = get_user_model()


def _generate_password() -> str:
    return secrets.token_urlsafe(12)


class Command(BaseCommand):
    help = "Create a superuser and one active example client organization."

    def add_arguments(self, parser):
        parser.add_argument("--admin-email", default="admin@heliograph.agency")
        parser.add_argument("--admin-password", default=None)
        parser.add_argument("--client-email", default="client@example.com")
        parser.add_argument("--client-password", default=None)
        parser.add_argument("--client-company", default="Example Client Co")
        parser.add_argument("--client-name", default="Example Client")

    def handle(self, *args, **options):
        generated = {}

        admin = self._ensure_admin(
            options["admin_email"], options["admin_password"], generated
        )
        client = self._ensure_client(
            options["client_email"], options["client_password"],
            options["client_company"], options["client_name"],
            admin, generated,
        )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"  Admin login:  {admin.email}")
        if "admin" in generated:
            self.stdout.write(f"  Admin password (generated): {generated['admin']}")
        self.stdout.write(f"  Client login: {client.email}")
        if "client" in generated:
            self.stdout.write(f"  Client password (generated): {generated['client']}")
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Store these credentials somewhere safe — generated passwords "
                "are not saved anywhere and are only printed once."
            )
        )

    @transaction.atomic
    def _ensure_admin(self, email, password, generated):
        email = User.objects.normalize_email(email).lower().strip()
        existing = User.objects.filter(email=email).first()
        if existing:
            if not existing.is_superuser:
                raise CommandError(
                    f"{email} already exists and is not a superuser; "
                    "pick a different --admin-email."
                )
            self.stdout.write(f"Admin {email} already exists — leaving it as-is.")
            return existing

        if password is None:
            password = _generate_password()
            generated["admin"] = password

        return User.objects.create_superuser(email=email, password=password, full_name="Admin")

    def _ensure_client(self, email, password, company, full_name, admin, generated):
        email = User.objects.normalize_email(email).lower().strip()
        existing = User.objects.filter(email=email).first()
        if existing:
            self.stdout.write(f"Client {email} already exists — leaving it as-is.")
            return existing

        if password is None:
            password = _generate_password()
            generated["client"] = password

        try:
            result = register_client(
                email=email, password=password, full_name=full_name, company_name=company,
            )
        except RegistrationError as exc:
            raise CommandError(str(exc)) from exc

        user = result.user
        if user.status != AccountStatus.ACTIVE:
            approve_account(user=user, actor=admin, reason="Seeded demo account")
            user.refresh_from_db()

        organization = result.organization
        if organization is not None and organization.status != OrganizationStatus.ACTIVE:
            activate_organization(
                organization=organization, actor=admin, reason="Seeded demo account"
            )

        return user
