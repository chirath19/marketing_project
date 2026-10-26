"""Test helpers for account fixtures."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from apps.accounts.models import AccountStatus, UserType

User = get_user_model()

PASSWORD = "correct-horse-battery"


def make_user(email: str = "client@example.com", *, password: str = PASSWORD,
              status: str = AccountStatus.ACTIVE,
              user_type: str = UserType.CLIENT, **extra):
    return User.objects.create_user(
        email=email, password=password, status=status,
        user_type=user_type, **extra,
    )


def make_staff(email: str = "staff@example.com", **extra):
    return make_user(email, user_type=UserType.STAFF, **extra)


def make_super_admin(email: str = "root@example.com", **extra):
    return make_user(email, user_type=UserType.SUPER_ADMIN, **extra)


REGISTRATION_POST = {
    "full_name": "Priya Raman",
    "email": "priya@vantage.example",
    "company_name": "Vantage Interiors",
    "job_title": "Marketing lead",
    "phone": "+94 11 234 5678",
    "password1": PASSWORD,
    "password2": PASSWORD,
    "website_url": "",
}
