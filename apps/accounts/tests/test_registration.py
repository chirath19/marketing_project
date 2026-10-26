"""Client registration."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts import services
from apps.accounts.models import AccountStatus, UserType
from apps.accounts.tests.factories import PASSWORD, REGISTRATION_POST, make_user
from apps.core.models import RateLimitEvent

User = get_user_model()

pytestmark = pytest.mark.django_db


# --- the happy path --------------------------------------------------------


def test_the_registration_page_renders(client):
    response = client.get(reverse("accounts:register"))

    assert response.status_code == 200
    # The form, not the headline: a copy edit to the heading should
    # not fail a test about whether registration is reachable.
    assert b'name="email"' in response.content
    assert b'name="password1"' in response.content


def test_registering_creates_a_pending_client_account(client):
    response = client.post(reverse("accounts:register"), REGISTRATION_POST)

    assert response.status_code == 302
    assert response.url == reverse("accounts:registration_pending")

    user = User.objects.get(email="priya@vantage.example")
    assert user.status == AccountStatus.PENDING
    assert user.user_type == UserType.CLIENT
    assert user.full_name == "Priya Raman"

    # The company is an Organization the user owns, not a column on the
    # user row — see apps/organizations.
    from apps.organizations.models import OrganizationMember
    membership = OrganizationMember.objects.get(user=user)
    assert membership.organization.name == "Vantage Interiors"
    assert membership.role == "owner"


def test_a_pending_registration_is_not_signed_in(client):
    """Approval would mean nothing if registering logged you in anyway."""
    client.post(reverse("accounts:register"), REGISTRATION_POST)

    assert "_auth_user_id" not in client.session


def test_the_password_is_hashed_not_stored(client):
    client.post(reverse("accounts:register"), REGISTRATION_POST)
    user = User.objects.get(email="priya@vantage.example")

    assert user.password != PASSWORD
    assert user.check_password(PASSWORD)


def test_the_pending_page_does_not_promise_an_email(client):
    """Nothing is sent outbound; telling someone to check their inbox
    would leave them waiting for something that never arrives.

    The page is allowed to *say* no email is coming — that is the honest
    thing to tell somebody — so this looks for the promise rather than
    for the word, which an outright denial would otherwise trip.
    """
    response = client.get(reverse("accounts:registration_pending"))
    body = response.content.decode().lower()

    assert response.status_code == 200
    for promise in ("check your inbox", "check your email",
                    "we have sent", "we've sent", "we will send you an email",
                    "click the link", "verification email has been"):
        assert promise not in body, promise

    # And it states the position plainly rather than leaving it unsaid.
    assert "no confirmation email is sent" in body


def test_an_authenticated_visitor_is_sent_away_from_registration(client):
    make_user()
    client.login(username="client@example.com", password=PASSWORD)

    response = client.get(reverse("accounts:register"))

    assert response.status_code == 302


# --- automatic activation mode --------------------------------------------


def test_auto_mode_activates_and_signs_the_client_in(client, settings):
    settings.ACCOUNTS_REGISTRATION_MODE = "auto"

    response = client.post(reverse("accounts:register"), REGISTRATION_POST)

    user = User.objects.get(email="priya@vantage.example")
    assert user.status == AccountStatus.ACTIVE
    assert client.session["_auth_user_id"] == str(user.pk)
    assert response.url == reverse("organizations:quote_create")
    assert client.get(response.url).status_code == 200


def test_approval_is_the_configured_default(settings):
    """The safer default: with no email verification, automatic
    activation would give any typed address a live account."""
    from django.conf import global_settings  # noqa: F401

    assert services.registration_requires_approval()


# --- duplicates ------------------------------------------------------------


def test_an_existing_email_is_rejected(client):
    make_user(email="priya@vantage.example")

    response = client.post(reverse("accounts:register"), REGISTRATION_POST)

    assert response.status_code == 200
    assert b"already exists" in response.content
    assert User.objects.filter(email="priya@vantage.example").count() == 1


def test_a_differently_cased_duplicate_is_rejected(client):
    """One person, one account — regardless of how they type it."""
    make_user(email="priya@vantage.example")

    response = client.post(
        reverse("accounts:register"), {**REGISTRATION_POST, "email": "PRIYA@Vantage.Example"}
    )

    assert response.status_code == 200
    assert User.objects.filter(email__iexact="priya@vantage.example").count() == 1


def test_an_email_with_surrounding_whitespace_is_normalised(client):
    client.post(reverse("accounts:register"),
                {**REGISTRATION_POST, "email": "  Priya@Vantage.Example  "})

    assert User.objects.filter(email="priya@vantage.example").exists()


def test_the_service_refuses_a_duplicate_even_if_the_form_is_bypassed():
    """The database constraint is the only thing that actually prevents a
    duplicate; the form check is for the message."""
    make_user(email="priya@vantage.example")

    with pytest.raises(services.RegistrationError, match="already exists"):
        services.register_client(email="PRIYA@vantage.example", password=PASSWORD)


# --- validation ------------------------------------------------------------


def test_mismatched_passwords_are_rejected(client):
    response = client.post(
        reverse("accounts:register"),
        {**REGISTRATION_POST, "password2": "something-else-entirely"},
    )

    assert response.status_code == 200
    assert b"do not match" in response.content
    assert not User.objects.filter(email="priya@vantage.example").exists()


@pytest.mark.parametrize("password", ["short", "password123", "12345678901"])
def test_a_weak_password_is_rejected(client, password):
    response = client.post(
        reverse("accounts:register"),
        {**REGISTRATION_POST, "password1": password, "password2": password},
    )

    assert response.status_code == 200
    assert not User.objects.filter(email="priya@vantage.example").exists()


def test_a_password_that_is_the_email_is_rejected(client):
    """Validated against the user's own details, not just a word list."""
    response = client.post(
        reverse("accounts:register"),
        {**REGISTRATION_POST, "password1": "priya@vantage.example",
         "password2": "priya@vantage.example"},
    )

    assert response.status_code == 200
    assert not User.objects.filter(email="priya@vantage.example").exists()


@pytest.mark.parametrize("missing", ["full_name", "email", "company_name"])
def test_required_fields_are_required(client, missing):
    response = client.post(reverse("accounts:register"),
                           {**REGISTRATION_POST, missing: ""})

    assert response.status_code == 200
    assert not User.objects.filter(email="priya@vantage.example").exists()


def test_an_invalid_email_is_rejected(client):
    response = client.post(reverse("accounts:register"),
                           {**REGISTRATION_POST, "email": "not-an-email"})

    assert response.status_code == 200
    assert User.objects.count() == 0


# --- abuse protection ------------------------------------------------------


def test_a_filled_honeypot_is_rejected(client):
    """People never see the field; naive bots fill every input."""
    response = client.post(reverse("accounts:register"),
                           {**REGISTRATION_POST, "website_url": "http://spam.example"})

    assert response.status_code == 200
    assert not User.objects.filter(email="priya@vantage.example").exists()


def test_the_honeypot_message_does_not_explain_the_trap(client):
    response = client.post(reverse("accounts:register"),
                           {**REGISTRATION_POST, "website_url": "spam"})

    assert b"honeypot" not in response.content.lower()
    assert b"could not be processed" in response.content


def test_registration_is_rate_limited_by_address(client):
    """Five an hour from one address. The sixth is refused — which also
    bounds how fast the duplicate-email message can be used to enumerate
    addresses."""
    for n in range(5):
        client.post(reverse("accounts:register"),
                    {**REGISTRATION_POST, "email": f"user{n}@example.com"})

    response = client.post(reverse("accounts:register"),
                           {**REGISTRATION_POST, "email": "user5@example.com"})

    assert response.status_code == 429
    assert not User.objects.filter(email="user5@example.com").exists()
    assert b"Too many attempts" in response.content


def test_invalid_submissions_count_towards_the_limit(client):
    """Otherwise an attacker gets unlimited attempts by sending rubbish."""
    for _ in range(5):
        client.post(reverse("accounts:register"), {**REGISTRATION_POST, "email": "bad"})

    response = client.post(reverse("accounts:register"), REGISTRATION_POST)

    assert response.status_code == 429
    assert not User.objects.filter(email="priya@vantage.example").exists()


def test_the_throttle_table_stores_no_raw_address(client):
    """It is a throttle, not an audit log: it needs to recognise a repeat
    caller, not identify one."""
    client.post(reverse("accounts:register"), REGISTRATION_POST)

    keys = list(RateLimitEvent.objects.values_list("key", flat=True))
    assert keys
    for key in keys:
        assert "127.0.0.1" not in key
        assert len(key) == 64  # sha256 hex digest
