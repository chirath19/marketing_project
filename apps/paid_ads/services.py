"""Validated, authorized writes shared by forms and CSV import."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.core.events import DomainEvent, bus
from apps.paid_ads import policies
from apps.paid_ads.models import MEASURES, REQUIRED_MEASURES, DailyAdMetric, PaidAdsGoal


@transaction.atomic
def record_metrics(
    *, organization, campaign, actor, date, platform, source, entry_method="manual", **values
):
    # Lock the parent so two upserts for the same daily key cannot both insert.
    from apps.campaigns.models import Campaign

    if not policies.can_write(actor, organization):
        raise PermissionDenied("You may not record advertising performance for this client.")
    if campaign.organization_id != organization.pk or campaign.service_type != "paid_ads":
        raise ValidationError("Choose this client's Paid Ads campaign.")
    campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.organization_id != organization.pk or campaign.service_type != "paid_ads":
        raise ValidationError("The campaign's client or service area has changed.")
    if set(values) - set(MEASURES):
        raise ValidationError("Unknown metric field.")
    missing_required = set(REQUIRED_MEASURES) - set(values)
    if missing_required:
        raise ValidationError(f"Missing required field(s): {', '.join(sorted(missing_required))}.")
    # Django's integer fields coerce fractional Decimal inputs to integers.
    # Refuse those inputs before model coercion can silently lose observations.
    # An optional measure left out entirely stays unreported (`None`) —
    # only a value that was actually supplied gets validated.
    for name in set(MEASURES) - {"spend", "revenue"}:
        if values.get(name) is None and name not in REQUIRED_MEASURES:
            continue
        try:
            value = Decimal(str(values.get(name)))
            if not value.is_finite() or value != value.to_integral_value():
                raise ValueError
        except (ValueError, InvalidOperation) as exc:
            raise ValidationError({name: "Enter a whole-number count."}) from exc
    record = DailyAdMetric.objects.filter(campaign=campaign, date=date, platform=platform).first()
    created = record is None
    if not created and not policies.can_write(actor, organization, "edit"):
        raise PermissionDenied("Correcting an existing daily record requires Paid Ads edit access.")
    if created:
        record = DailyAdMetric(
            organization=organization,
            campaign=campaign,
            date=date,
            platform=platform,
            currency=campaign.currency.upper(),
        )
    for name in MEASURES:
        setattr(record, name, values.get(name))
    record.source = source.strip()
    record.entry_method = entry_method
    record.recorded_by = actor
    record.full_clean()
    record.save()
    bus.publish(
        DomainEvent(
            "paid_ads.metrics_recorded",
            {
                "record_id": record.pk,
                "organization_id": organization.pk,
                "actor_id": actor.pk,
                "created": created,
            },
        )
    )
    return record


@transaction.atomic
def save_goal(*, organization, actor, goal=None, **fields):
    action = "edit" if goal else "create"
    if not policies.can_write(actor, organization, action):
        raise PermissionDenied("You may not manage advertising goals for this client.")
    if goal and goal.organization_id != organization.pk:
        raise PermissionDenied("That goal belongs to another client.")
    allowed = {
        "title",
        "metric",
        "target",
        "starts_on",
        "ends_on",
        "currency",
        "platform",
        "campaign",
        "is_active",
    }
    if set(fields) - allowed:
        raise ValidationError("Unknown goal field.")
    goal = goal or PaidAdsGoal(organization=organization)
    for key, value in fields.items():
        setattr(goal, key, value)
    goal.full_clean()
    goal.save()
    bus.publish(
        DomainEvent(
            "paid_ads.goal_saved",
            {
                "goal_id": goal.pk,
                "organization_id": organization.pk,
                "actor_id": actor.pk,
            },
        )
    )
    return goal
