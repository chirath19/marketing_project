from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, connections, transaction

from apps.approvals import services
from apps.approvals.models import ApprovalRequest
from apps.organizations.models import Organization


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_simultaneous_decisions_have_one_winner(workspace, approval):
    barrier = Barrier(2)

    def decide(decision):
        close_old_connections()
        try:
            actor = get_user_model().objects.get(pk=workspace["user"].pk)
            organization = Organization.objects.get(pk=workspace["org"].pk)
            request = ApprovalRequest.objects.get(pk=approval.pk)
            barrier.wait(timeout=10)
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '5s'")
                    services.decide(
                        actor=actor,
                        organization=organization,
                        request=request,
                        decision=decision,
                        response="Concurrent client response",
                    )
                return "resolved"
            except ValidationError:
                return "already-resolved"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(decide, decision) for decision in ("approved", "rejected")]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(results) == ["already-resolved", "resolved"]
    approval.refresh_from_db()
    assert approval.status in {"approved", "rejected"}
    assert approval.history.filter(kind="decided").count() == 1
