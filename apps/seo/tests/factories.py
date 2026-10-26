"""Test helpers for the SEO module."""

from __future__ import annotations

from datetime import date

from apps.seo.models import AuditStatus, BacklinkStatus, TaskKind, TaskStatus

__all__ = ["make_audit", "make_issue", "make_keyword", "make_position",
           "make_task", "make_backlink", "make_goal"]


def _admin():  # noqa: ANN202
    """A super admin to act as, reused across calls.

    Created once per test rather than per call: these helpers are used
    several times in a single test, and a factory that insisted on a new
    account each time would collide on the unique email.
    """
    from django.contrib.auth import get_user_model

    from apps.staff.tests.factories import make_super_admin_user

    email = "seo-setup@heliograph.agency"
    existing = get_user_model().objects.filter(email=email).first()
    return existing or make_super_admin_user(email)


def make_audit(organization, *, actor=None, title: str = "Technical audit",  # noqa: ANN001
               status: str = AuditStatus.IN_PROGRESS, **fields):  # noqa: ANN201
    """An audit, built the way the real one is — through the service layer."""
    from apps.seo.services import create_audit

    audit = create_audit(organization=organization, title=title,
                         actor=actor or _admin(), **fields)
    if status != AuditStatus.IN_PROGRESS:
        audit.status = status
        audit.save(update_fields=["status"])
    return audit


def make_issue(audit, *, actor=None, title: str = "Slow pages", **fields):  # noqa: ANN001, ANN201
    from apps.seo.services import add_issue

    return add_issue(audit=audit, title=title, actor=actor or _admin(), **fields)


def make_keyword(organization, *, actor=None, term: str = "interior designer",  # noqa: ANN001
                 **fields):  # noqa: ANN201
    from apps.seo.services import add_keyword

    return add_keyword(organization=organization, term=term,
                       actor=actor or _admin(), **fields)


def make_position(keyword, *, actor=None, position: int = 7,  # noqa: ANN001
                  recorded_on: date | None = None, source: str = "Manual"):  # noqa: ANN201
    from django.utils import timezone

    from apps.seo.services import record_position

    return record_position(
        keyword=keyword, actor=actor or _admin(),
        recorded_on=recorded_on or timezone.localdate(),
        position=position, source=source,
    )


def make_task(organization, *, actor=None, title: str = "Rewrite the homepage",  # noqa: ANN001
              kind: str = TaskKind.CONTENT, status: str = TaskStatus.PLANNED,
              **fields):  # noqa: ANN201
    from apps.seo.services import create_task

    return create_task(organization=organization, title=title,
                       actor=actor or _admin(), kind=kind, status=status,
                       **fields)


def make_backlink(organization, *, actor=None,  # noqa: ANN001
                  source_domain: str = "trade-journal.example",
                  status: str = BacklinkStatus.PROSPECT, **fields):  # noqa: ANN201
    from apps.seo.services import record_backlink

    return record_backlink(organization=organization,
                           source_domain=source_domain,
                           actor=actor or _admin(), status=status, **fields)


def make_goal(organization, *, metric: str = "top_10", target: int = 10,  # noqa: ANN001
              **fields):  # noqa: ANN201
    from apps.seo.models import SeoGoal

    return SeoGoal.objects.create(organization=organization, metric=metric,
                                  target=target, **fields)
