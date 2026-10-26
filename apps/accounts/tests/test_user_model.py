"""The user model is the one piece of P1 that cannot be deferred, so its
invariants are worth locking down now."""

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import UserType

User = get_user_model()


@pytest.mark.django_db
def test_create_user_defaults_to_the_client_type():
    user = User.objects.create_user(email="sam@example.com", password="correct-horse-1")

    assert user.user_type == UserType.CLIENT
    assert user.is_client
    assert not user.is_staff_member
    assert not user.is_staff


@pytest.mark.django_db
def test_create_superuser_is_a_super_admin():
    user = User.objects.create_superuser(email="root@example.com", password="correct-horse-1")

    assert user.user_type == UserType.SUPER_ADMIN
    assert user.is_super_admin
    assert user.is_staff_member
    assert user.is_superuser


@pytest.mark.django_db
def test_email_is_lower_cased_so_one_person_cannot_hold_two_accounts():
    user = User.objects.create_user(email="Sam.K@Example.COM", password="correct-horse-1")

    assert user.email == "sam.k@example.com"


@pytest.mark.django_db
def test_email_is_normalised_even_when_set_directly():
    """Not every write goes through the manager."""
    user = User(email="MIXED@Example.com")
    user.set_password("correct-horse-1")
    user.save()
    user.refresh_from_db()

    assert user.email == "mixed@example.com"


@pytest.mark.django_db
def test_duplicate_emails_are_rejected_regardless_of_case():
    from django.db import IntegrityError

    User.objects.create_user(email="dup@example.com", password="correct-horse-1")

    with pytest.raises(IntegrityError):
        User.objects.create_user(email="DUP@example.com", password="correct-horse-1")


@pytest.mark.django_db
def test_a_user_without_an_email_is_rejected():
    with pytest.raises(ValueError, match="email address"):
        User.objects.create_user(email="", password="correct-horse-1")


@pytest.mark.django_db
def test_superuser_flags_cannot_be_contradicted():
    with pytest.raises(ValueError, match="is_staff=True"):
        User.objects.create_superuser(
            email="x@example.com", password="correct-horse-1", is_staff=False
        )

    with pytest.raises(ValueError, match="is_superuser=True"):
        User.objects.create_superuser(
            email="y@example.com", password="correct-horse-1", is_superuser=False
        )


@pytest.mark.django_db
def test_staff_user_type_is_distinct_from_django_admin_access():
    """A staff dashboard user is not automatically a Django admin user."""
    user = User.objects.create_user(
        email="staff@example.com", password="correct-horse-1", user_type=UserType.STAFF
    )

    assert user.is_staff_member
    assert not user.is_staff


@pytest.mark.django_db
def test_display_names_fall_back_to_the_email():
    user = User.objects.create_user(email="noname@example.com", password="correct-horse-1")

    assert user.get_full_name() == "noname@example.com"
    assert user.get_short_name() == "noname@example.com"

    user.full_name = "Amara Silva"
    assert user.get_short_name() == "Amara"


@pytest.mark.django_db
def test_password_is_hashed_not_stored():
    user = User.objects.create_user(email="pw@example.com", password="correct-horse-1")

    assert user.password != "correct-horse-1"
    assert user.check_password("correct-horse-1")
