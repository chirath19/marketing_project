"""Account status: the state machine and who may drive it."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts import services
from apps.accounts.models import AccountStatus
from apps.accounts.tests.factories import make_staff, make_super_admin, make_user

pytestmark = pytest.mark.django_db


# --- is_active is derived --------------------------------------------------


def test_only_an_active_account_is_treated_as_active():
    assert make_user(email="a@example.com").is_active
    assert not make_user(email="b@example.com", status=AccountStatus.PENDING).is_active
    assert not make_user(email="c@example.com", status=AccountStatus.SUSPENDED).is_active
    assert not make_user(email="d@example.com", status=AccountStatus.DISABLED).is_active


def test_is_active_cannot_be_set_directly():
    """Two columns that must agree eventually disagree, and the failure
    mode is a suspended account that can still sign in."""
    user = make_user()

    with pytest.raises(AttributeError):
        user.is_active = False


def test_is_active_is_not_a_database_column():
    from django.contrib.auth import get_user_model

    fields = {f.name for f in get_user_model()._meta.get_fields()}
    assert "is_active" not in fields
    assert "status" in fields


# --- the state machine -----------------------------------------------------


def test_approving_a_pending_account_activates_it():
    user = make_user(status=AccountStatus.PENDING)
    staff = make_super_admin()

    services.approve_account(user=user, actor=staff, reason="Scoped and signed")
    user.refresh_from_db()

    assert user.status == AccountStatus.ACTIVE
    assert user.status_changed_at is not None
    assert user.status_reason == "Scoped and signed"


def test_a_suspended_account_can_be_reactivated():
    user = make_user(status=AccountStatus.SUSPENDED)
    staff = make_super_admin()

    services.reactivate_account(user=user, actor=staff)
    user.refresh_from_db()

    assert user.status == AccountStatus.ACTIVE


@pytest.mark.parametrize(
    ("start", "target"),
    [(AccountStatus.PENDING, AccountStatus.SUSPENDED),
     (AccountStatus.DISABLED, AccountStatus.SUSPENDED),
     (AccountStatus.DISABLED, AccountStatus.PENDING),
     (AccountStatus.ACTIVE, AccountStatus.PENDING)],
)
def test_an_undefined_transition_is_refused(start, target):
    """Declared as data, so an unlisted move raises rather than quietly
    succeeding — the bug that otherwise surfaces as a reactivated account
    nobody authorised."""
    user = make_user(status=start)
    staff = make_super_admin()

    with pytest.raises(ValidationError):
        services.change_status(user=user, new_status=target, actor=staff)

    user.refresh_from_db()
    assert user.status == start


def test_moving_to_the_same_status_is_a_no_op():
    user = make_user(status=AccountStatus.ACTIVE)
    staff = make_super_admin()

    services.change_status(user=user, new_status=AccountStatus.ACTIVE, actor=staff)
    user.refresh_from_db()

    assert user.status == AccountStatus.ACTIVE
    assert user.status_changed_at is None, "an unchanged status should not be stamped"


def test_an_unknown_status_value_is_refused():
    user = make_user()

    with pytest.raises(ValidationError):
        services.change_status(user=user, new_status="vaporised",
                               actor=make_super_admin())


def test_a_disabled_account_is_kept_rather_than_deleted():
    """Leads, approvals and messages reference it; deleting would take
    their history with it."""
    from django.contrib.auth import get_user_model

    user = make_user()
    services.disable_account(user=user, actor=make_super_admin())

    assert get_user_model().objects.filter(pk=user.pk).exists()
    user.refresh_from_db()
    assert user.status == AccountStatus.DISABLED


# --- who may change a status ----------------------------------------------


def test_a_client_cannot_change_any_account_status():
    client_user = make_user(email="client@example.com")
    other = make_user(email="other@example.com", status=AccountStatus.PENDING)

    with pytest.raises(PermissionDenied):
        services.approve_account(user=other, actor=client_user)


def test_a_client_cannot_approve_their_own_account():
    """The whole point of pending is that someone else decides."""
    user = make_user(status=AccountStatus.PENDING)

    with pytest.raises(PermissionDenied):
        services.approve_account(user=user, actor=user)


def test_nobody_changes_their_own_status_not_even_a_super_admin():
    """Otherwise a suspended account with a live session lifts its own
    suspension."""
    admin = make_super_admin()

    with pytest.raises(PermissionDenied):
        services.suspend_account(user=admin, actor=admin)


def test_staff_may_act_on_a_client():
    staff = make_staff()
    client_user = make_user(status=AccountStatus.PENDING)

    services.approve_account(user=client_user, actor=staff)
    client_user.refresh_from_db()

    assert client_user.status == AccountStatus.ACTIVE


def test_staff_may_not_act_on_another_staff_member():
    """A staff account must not be able to disable its own supervisor."""
    staff = make_staff(email="one@example.com")
    colleague = make_staff(email="two@example.com")

    with pytest.raises(PermissionDenied):
        services.suspend_account(user=colleague, actor=staff)


def test_a_super_admin_may_act_on_a_staff_member():
    admin = make_super_admin()
    staff = make_staff()

    services.suspend_account(user=staff, actor=admin)
    staff.refresh_from_db()

    assert staff.status == AccountStatus.SUSPENDED


def test_an_anonymous_actor_cannot_change_a_status():
    from django.contrib.auth.models import AnonymousUser

    user = make_user(status=AccountStatus.PENDING)

    with pytest.raises(PermissionDenied):
        services.approve_account(user=user, actor=AnonymousUser())


# --- events ----------------------------------------------------------------


# The bus dispatches inside `transaction.on_commit`, so a handler can
# never react to a change that later rolls back. Tests run in a
# transaction that is never committed, so they capture the callbacks
# instead of waiting for a commit that will not come.


def test_a_status_change_publishes_an_event(django_capture_on_commit_callbacks):
    """Notifications and audit subscribe to this rather than the accounts
    app importing either of them."""
    from apps.core.events import DomainEvent, bus

    received: list[DomainEvent] = []
    bus.subscribe("account.status_changed", received.append)
    try:
        user = make_user(status=AccountStatus.PENDING)
        with django_capture_on_commit_callbacks(execute=True):
            services.approve_account(user=user, actor=make_super_admin(), reason="ok")
    finally:
        bus.unsubscribe("account.status_changed", received.append)

    assert len(received) == 1
    assert received[0].payload["to_status"] == AccountStatus.ACTIVE
    assert received[0].payload["from_status"] == AccountStatus.PENDING


def test_registration_publishes_an_event(django_capture_on_commit_callbacks):
    from apps.core.events import DomainEvent, bus

    received: list[DomainEvent] = []
    bus.subscribe("account.registered", received.append)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            services.register_client(email="new@example.com",
                                     password="correct-horse-battery")
    finally:
        bus.unsubscribe("account.registered", received.append)

    assert len(received) == 1
    assert received[0].payload["requires_approval"] is True


def test_a_rolled_back_registration_publishes_nothing():
    """The event must describe something that actually happened."""
    from django.db import transaction

    from apps.core.events import DomainEvent, bus

    received: list[DomainEvent] = []
    bus.subscribe("account.registered", received.append)
    try:
        with pytest.raises(RuntimeError), transaction.atomic():
            services.register_client(email="ghost@example.com",
                                     password="correct-horse-battery")
            raise RuntimeError("something later failed")
    finally:
        bus.unsubscribe("account.registered", received.append)

    assert received == []


# --- superusers ------------------------------------------------------------


def test_a_superuser_is_created_active():
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_superuser(
        email="root@example.com", password="correct-horse-battery"
    )

    assert user.status == AccountStatus.ACTIVE
    assert user.is_active


def test_a_superuser_cannot_be_created_inactive():
    from django.contrib.auth import get_user_model

    with pytest.raises(ValueError, match="must be active"):
        get_user_model().objects.create_superuser(
            email="root@example.com", password="correct-horse-battery",
            status=AccountStatus.SUSPENDED,
        )
