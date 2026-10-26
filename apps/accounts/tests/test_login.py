"""Sign in, and the account statuses that block it."""

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.urls import reverse

from apps.accounts.models import AccountStatus
from apps.accounts.tests.factories import PASSWORD, make_user

User = get_user_model()

pytestmark = pytest.mark.django_db

LOGIN = "/accounts/login/"


def post_login(client, email=    "client@example.com", password=PASSWORD):
    return client.post(reverse("accounts:login"),
                       {"username": email, "password": password})


# --- the happy path --------------------------------------------------------


def test_the_login_page_renders(client):
    response = client.get(reverse("accounts:login"))

    assert response.status_code == 200
    assert b"Email address" in response.content


def test_an_active_user_can_sign_in(client):
    user = make_user()

    response = post_login(client)

    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(user.pk)


def test_sign_in_is_case_insensitive_on_the_email(client):
    """Addresses are stored lower-cased, so the lookup is too."""
    make_user(email="sam@example.com")

    response = post_login(client, email="SAM@Example.COM")

    assert response.status_code == 302


def test_signing_out_clears_the_session(client):
    make_user()
    post_login(client)
    assert "_auth_user_id" in client.session

    response = client.post(reverse("accounts:logout"))

    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


# --- invalid credentials ---------------------------------------------------


def test_a_wrong_password_is_refused(client):
    make_user()

    response = post_login(client, password="not-the-password")

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


def test_an_unknown_address_is_refused(client):
    response = post_login(client, email="nobody@example.com")

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


def test_a_wrong_password_does_not_reveal_whether_the_account_exists(client):
    """The form must not be an account-existence oracle."""
    make_user(email="real@example.com")

    known = post_login(client, email="real@example.com", password="wrong-password-99")
    unknown = post_login(client, email="ghost@example.com", password="wrong-password-99")

    assert known.status_code == unknown.status_code == 200
    assert b"Please enter a correct" in known.content
    assert b"Please enter a correct" in unknown.content


@pytest.mark.parametrize("status", [AccountStatus.PENDING, AccountStatus.SUSPENDED,
                                    AccountStatus.DISABLED])
def test_a_wrong_password_on_an_inactive_account_still_says_nothing(client, status):
    """The status explanation is only ever reached with the correct
    password, so it tells an attacker nothing they could not infer."""
    make_user(status=status)

    response = post_login(client, password="wrong-password-99")

    assert b"Please enter a correct" in response.content
    assert b"waiting for approval" not in response.content
    assert b"suspended" not in response.content


# --- inactive accounts -----------------------------------------------------


@pytest.mark.parametrize("status", [AccountStatus.PENDING, AccountStatus.SUSPENDED,
                                    AccountStatus.DISABLED])
def test_a_non_active_account_cannot_sign_in(client, status):
    make_user(status=status)

    response = post_login(client)

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("status", [AccountStatus.PENDING, AccountStatus.SUSPENDED,
                                    AccountStatus.DISABLED])
def test_the_backend_itself_refuses_a_non_active_account(status):
    """Not just the form. `authenticate()` must return None, so no other
    entry point — API, management command, a future SSO backend — can let
    a suspended account through."""
    make_user(status=status)

    assert authenticate(username="client@example.com", password=PASSWORD) is None


def test_the_backend_accepts_an_active_account():
    make_user()

    assert authenticate(username="client@example.com", password=PASSWORD) is not None


def test_a_pending_user_is_told_their_account_awaits_approval(client):
    """With nothing sent outbound, a generic failure would leave them with
    no way to find out what happened."""
    make_user(status=AccountStatus.PENDING)

    response = post_login(client)

    assert b"waiting for approval" in response.content


def test_a_suspended_user_is_told_to_contact_their_account_manager(client):
    make_user(status=AccountStatus.SUSPENDED)

    response = post_login(client)

    assert b"suspended" in response.content


def test_a_disabled_user_is_told_the_account_is_closed(client):
    make_user(status=AccountStatus.DISABLED)

    response = post_login(client)

    assert b"closed" in response.content


def test_suspending_an_account_does_not_end_an_existing_session_silently(client):
    """A suspended user keeps a signed cookie until it is checked. Django
    re-validates against the database on each request, so the next one
    logs them out — this pins that behaviour down rather than assuming
    it."""
    user = make_user()
    post_login(client)

    user.status = AccountStatus.SUSPENDED
    user.save(update_fields=["status"])

    response = client.get(reverse("accounts:profile"))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


# --- rate limiting ---------------------------------------------------------


def test_sign_in_is_rate_limited_per_account(client):
    """Ten attempts per account in fifteen minutes."""
    make_user()

    for _ in range(10):
        post_login(client, password="wrong-password-99")

    response = post_login(client, password="wrong-password-99")

    assert response.status_code == 429
    assert b"Too many attempts" in response.content


def test_the_account_limit_blocks_even_the_correct_password(client):
    """Otherwise the limit would do nothing against a password guess that
    eventually lands."""
    make_user()

    for _ in range(10):
        post_login(client, password="wrong-password-99")

    response = post_login(client)

    assert response.status_code == 429
    assert "_auth_user_id" not in client.session


def test_a_successful_sign_in_clears_the_accounts_counter(client):
    """A legitimate user who mistyped twice should not be punished for
    then getting it right."""
    from apps.core.ratelimit import LOGIN_ACCOUNT, peek

    make_user()
    for _ in range(3):
        post_login(client, password="wrong-password-99")

    post_login(client)

    assert peek(LOGIN_ACCOUNT, "client@example.com").remaining == LOGIN_ACCOUNT.limit


def test_one_accounts_lockout_does_not_lock_out_another(client):
    """Account-scoped, not address-scoped, up to the address limit."""
    make_user(email="first@example.com")
    make_user(email="second@example.com")

    for _ in range(10):
        post_login(client, email="first@example.com", password="wrong-password-99")

    response = post_login(client, email="second@example.com")

    assert response.status_code == 302
