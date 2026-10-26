"""Authorization: who can reach what, enforced on the server.

Hidden UI is never a control, so every one of these drives the real URL
rather than checking whether a link was rendered.
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.accounts import policies, selectors, services
from apps.accounts.models import AccountStatus
from apps.accounts.tests.factories import (
    PASSWORD,
    make_staff,
    make_super_admin,
    make_user,
)

pytestmark = pytest.mark.django_db

PROTECTED_URLS = [
    "accounts:profile",
    "accounts:password_change",
]


# --- anonymous access ------------------------------------------------------


@pytest.mark.parametrize("url_name", PROTECTED_URLS)
def test_an_anonymous_visitor_is_sent_to_sign_in(client, url_name):
    response = client.get(reverse(url_name))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.parametrize("url_name", PROTECTED_URLS)
def test_an_anonymous_post_is_refused_too(client, url_name):
    """A guard that only covers GET is not a guard."""
    response = client.post(reverse(url_name), {})

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


# --- signed-in access ------------------------------------------------------


@pytest.mark.parametrize("url_name", PROTECTED_URLS)
def test_a_signed_in_user_reaches_their_own_pages(client, url_name):
    make_user()
    client.login(username="client@example.com", password=PASSWORD)

    assert client.get(reverse(url_name)).status_code == 200


def test_a_user_only_ever_edits_their_own_profile(client):
    """The view binds the form to request.user, so there is no id in the
    request for an attacker to swap."""
    make_user(email="mine@example.com", full_name="Mine")
    other = make_user(email="theirs@example.com", full_name="Theirs")
    client.login(username="mine@example.com", password=PASSWORD)

    client.post(reverse("accounts:profile"), {
        "full_name": "Changed", "phone": "", "job_title": "",
        "id": other.pk, "user": other.pk,
    })

    other.refresh_from_db()
    assert other.full_name == "Theirs"


def test_the_profile_service_refuses_an_actor_editing_someone_else(client):
    mine = make_user(email="mine@example.com")
    theirs = make_user(email="theirs@example.com")

    with pytest.raises(PermissionDenied):
        services.update_profile(user=theirs, actor=mine, full_name="Hijacked")


def test_the_profile_service_refuses_fields_it_does_not_own(client):
    """A crafted POST naming `status` or `email` must not be accepted just
    because it reached a service function."""
    from django.core.exceptions import ValidationError

    user = make_user()

    with pytest.raises(ValidationError):
        services.update_profile(user=user, actor=user, status="active")

    with pytest.raises(ValidationError):
        # The company belongs to the organization now, not the user.
        services.update_profile(user=user, actor=user, company_name="Hijacked Ltd")

    with pytest.raises(ValidationError):
        services.update_profile(user=user, actor=user, email="new@example.com")


def test_the_profile_form_cannot_change_the_login_email(client):
    """Email is the login identifier and nothing outbound can verify a
    change, so a typo would silently lock someone out."""
    make_user(email="mine@example.com")
    client.login(username="mine@example.com", password=PASSWORD)

    client.post(reverse("accounts:profile"), {
        "full_name": "Still Mine", "phone": "", "job_title": "",
        "email": "hijacked@example.com",
    })

    assert not selectors.email_is_taken("hijacked@example.com")
    assert selectors.email_is_taken("mine@example.com")


def test_a_user_can_edit_their_own_profile(client):
    user = make_user()
    client.login(username="client@example.com", password=PASSWORD)

    client.post(reverse("accounts:profile"), {
        "full_name": "Priya Raman", "phone": "+94 11 234", "job_title": "Lead",
    })

    user.refresh_from_db()
    assert user.full_name == "Priya Raman"
    assert user.job_title == "Lead"


# --- password change -------------------------------------------------------


def test_changing_a_password_requires_the_current_one(client):
    """Otherwise a borrowed session locks the real owner out."""
    user = make_user()
    client.login(username="client@example.com", password=PASSWORD)

    response = client.post(reverse("accounts:password_change"), {
        "old_password": "not-the-current-one",
        "new_password1": "a-brand-new-secret-1",
        "new_password2": "a-brand-new-secret-1",
    })

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_a_user_can_change_their_own_password(client):
    user = make_user()
    client.login(username="client@example.com", password=PASSWORD)

    response = client.post(reverse("accounts:password_change"), {
        "old_password": PASSWORD,
        "new_password1": "a-brand-new-secret-1",
        "new_password2": "a-brand-new-secret-1",
    })

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password("a-brand-new-secret-1")


def test_changing_a_password_keeps_the_session_alive(client):
    make_user()
    client.login(username="client@example.com", password=PASSWORD)

    client.post(reverse("accounts:password_change"), {
        "old_password": PASSWORD,
        "new_password1": "a-brand-new-secret-1",
        "new_password2": "a-brand-new-secret-1",
    })

    assert client.get(reverse("accounts:profile")).status_code == 200


def test_a_weak_new_password_is_refused(client):
    user = make_user()
    client.login(username="client@example.com", password=PASSWORD)

    client.post(reverse("accounts:password_change"), {
        "old_password": PASSWORD, "new_password1": "abc", "new_password2": "abc",
    })

    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_staff_may_not_set_a_clients_password():
    """With nothing outbound there is no safe way to deliver a new one, so
    a staff-initiated reset is a separate, auditable flow — not a quiet
    capability here."""
    client_user = make_user(email="client@example.com")

    assert not policies.can_change_password(make_staff(), client_user)
    assert not policies.can_change_password(make_super_admin(), client_user)
    assert policies.can_change_password(client_user, client_user)


# --- what a user may see ---------------------------------------------------


def test_a_client_only_sees_their_own_account_in_a_listing():
    mine = make_user(email="mine@example.com")
    make_user(email="theirs@example.com")

    visible = selectors.visible_accounts(mine)

    assert list(visible.values_list("email", flat=True)) == ["mine@example.com"]


def test_staff_see_every_account():
    staff = make_staff()
    make_user(email="a@example.com")
    make_user(email="b@example.com")

    assert selectors.visible_accounts(staff).count() == 3


def test_an_anonymous_actor_sees_nothing():
    assert selectors.visible_accounts(AnonymousUser()).count() == 0
    assert selectors.visible_accounts(None).count() == 0


def test_pending_approvals_are_staff_only_and_oldest_first():
    staff = make_staff()
    make_user(email="first@example.com", status=AccountStatus.PENDING)
    make_user(email="second@example.com", status=AccountStatus.PENDING)
    make_user(email="active@example.com")

    pending = list(selectors.pending_approvals(staff).values_list("email", flat=True))

    assert pending == ["first@example.com", "second@example.com"]
    assert selectors.pending_approvals(make_user(email="c@example.com")).count() == 0


# --- the Django admin ------------------------------------------------------


def test_a_client_cannot_reach_the_django_admin(client):
    make_user()
    client.login(username="client@example.com", password=PASSWORD)

    response = client.get("/admin/")

    assert response.status_code == 302
    assert "/admin/login/" in response.url


def test_a_staff_user_type_alone_does_not_grant_django_admin(client):
    """`is_staff` is Django admin access; the Staff user type is the staff
    dashboard. Conflating them would hand the admin to every account
    manager."""
    staff = make_staff()
    assert staff.is_staff_member
    assert not staff.is_staff

    client.login(username="staff@example.com", password=PASSWORD)
    response = client.get("/admin/")

    assert response.status_code == 302


def test_editing_a_profile_actually_persists_every_changed_field():
    """A ModelForm writes submitted values onto its instance during
    validation, so a service that diffs old against new sees no change
    and saves nothing. The profile form is deliberately not a ModelForm;
    this is the guard."""
    user = make_user(full_name="Old Name", job_title="Old Title")

    services.update_profile(user=user, actor=user, full_name="New Name",
                            job_title="New Title", phone="")

    user.refresh_from_db()
    assert user.full_name == "New Name"
    assert user.job_title == "New Title"


def test_editing_a_profile_trims_surrounding_whitespace():
    user = make_user()

    services.update_profile(user=user, actor=user, full_name="  Priya Raman  ")

    user.refresh_from_db()
    assert user.full_name == "Priya Raman"


def test_an_unchanged_profile_publishes_no_event(django_capture_on_commit_callbacks):
    """Nothing happened, so nothing should be announced as having."""
    from apps.core.events import DomainEvent, bus

    user = make_user(full_name="Same")
    received: list[DomainEvent] = []
    bus.subscribe("account.profile_updated", received.append)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            services.update_profile(user=user, actor=user, full_name="Same")
    finally:
        bus.unsubscribe("account.profile_updated", received.append)

    assert received == []


def test_staff_may_edit_a_clients_profile():
    staff = make_staff()
    client_user = make_user()

    services.update_profile(user=client_user, actor=staff, full_name="Corrected")

    client_user.refresh_from_db()
    assert client_user.full_name == "Corrected"
