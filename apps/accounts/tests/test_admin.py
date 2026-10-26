"""The Django admin is a real entry point, so its actions are tested too."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage

from apps.accounts.admin import UserAdmin
from apps.accounts.models import AccountStatus
from apps.accounts.tests.factories import make_staff, make_super_admin, make_user

User = get_user_model()
pytestmark = pytest.mark.django_db


def admin_request(rf, actor):  # noqa: ANN001, ANN201
    request = rf.post("/admin/accounts/user/")
    request.user = actor
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


@pytest.fixture
def user_admin():
    return UserAdmin(User, AdminSite())


def test_the_approve_action_activates_pending_accounts(rf, user_admin):
    admin = make_super_admin()
    pending = make_user(status=AccountStatus.PENDING)

    user_admin.approve_accounts(admin_request(rf, admin), User.objects.all())

    pending.refresh_from_db()
    assert pending.status == AccountStatus.ACTIVE


def test_the_approve_action_leaves_non_pending_accounts_alone(rf, user_admin):
    admin = make_super_admin()
    active = make_user(status=AccountStatus.ACTIVE)

    user_admin.approve_accounts(admin_request(rf, admin), User.objects.all())

    active.refresh_from_db()
    assert active.status == AccountStatus.ACTIVE
    admin.refresh_from_db()
    assert admin.status == AccountStatus.ACTIVE


def test_an_admin_action_cannot_bypass_the_policy(rf, user_admin):
    """Staff may not act on another staff member — the action calls the
    same service as everything else, so the rule holds here too."""
    staff = make_staff(email="one@example.com")
    colleague = make_staff(email="two@example.com")

    user_admin.suspend_accounts(admin_request(rf, staff), User.objects.all())

    colleague.refresh_from_db()
    assert colleague.status == AccountStatus.ACTIVE


def test_an_admin_action_records_who_made_the_change(rf, user_admin):
    admin = make_super_admin(email="root@example.com")
    pending = make_user(status=AccountStatus.PENDING)

    user_admin.approve_accounts(admin_request(rf, admin), User.objects.all())

    pending.refresh_from_db()
    assert "root@example.com" in pending.status_reason
    assert pending.status_changed_at is not None


def test_status_is_not_directly_editable_in_the_admin(user_admin):
    """Setting it by hand would skip the transition rules, the reason,
    the timestamp and the event."""
    assert "status" in user_admin.readonly_fields
    assert "status_changed_at" in user_admin.readonly_fields
