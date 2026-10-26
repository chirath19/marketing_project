"""Client service-change requests, priced and accepted through ordinary quotations."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.features import require
from apps.leads.models import QuoteStatus
from apps.leads.services import record_submission
from apps.notifications.services import notify
from apps.organizations.selectors import membership_for
from apps.permissions.access import can
from apps.subscriptions.models import ClientSubscription, ServiceChangeRequest, SubscriptionStatus


def visible(actor, organization=None):
    from apps.permissions.guards import scope_to_accessible

    require("service_requests", actor)
    rows = ServiceChangeRequest.objects.select_related(
        "quote", "subscription", "client", "organization"
    )
    if actor.is_staff_member:
        if not can(actor, "subscriptions_view"):
            return rows.none()
        rows = scope_to_accessible(rows, actor)
    else:
        if (
            not organization
            or not membership_for(actor, organization)
            or not organization.is_operational
        ):
            return rows.none()
        rows = rows.filter(client=actor, organization=organization)
    return rows


@transaction.atomic
def request_change(
    *, actor, subscription, kind, requirements, requested_end=None, additional_service=None
):
    require("service_requests", actor)
    member = membership_for(actor, subscription.organization)
    if (
        not actor.is_active
        or not actor.is_client
        or not member
        or member.role == "viewer"
        or not subscription.organization.is_operational
    ):
        raise PermissionDenied
    if kind not in {"renewal", "extension", "extra", "additional"} or not requirements.strip():
        raise ValidationError("Choose a request type and describe the work.")
    if len(requirements) > 5000:
        raise ValidationError("Keep the request under 5,000 characters.")
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise ValidationError("Request a new quotation for a cancelled service.")
    if kind in {"renewal", "extension"} and (not requested_end or requested_end <= max(
        subscription.ends_on or timezone.localdate(), timezone.localdate()
    )):
        raise ValidationError("Choose an end date after the current service period and today.")
    if kind == "additional" and (
        not additional_service
        or not additional_service.is_active
        or not additional_service.is_visible
        or not additional_service.can_request_quote
    ):
        raise ValidationError("Choose an available additional service.")
    if kind != "additional":
        additional_service = None
    service = additional_service or subscription.service
    details = f"{kind.title()} for {subscription.name}.\n{requirements.strip()}"
    if requested_end:
        details += f"\nRequested end date: {requested_end.isoformat()}."
    submission = record_submission(
        name=actor.get_full_name(),
        email=actor.email,
        company=subscription.organization.name,
        message=details,
        kind="quote_request",
        source="quote_builder",
        subject=f"Service {kind}",
        submitted_by=actor,
        organization=subscription.organization,
        quote_items=[
            {
                "service": service,
                "name": f"{kind.title()}: {service.name}",
                "price_display": "",
                "billing_display": "",
            }
        ],
    )
    return ServiceChangeRequest.objects.create(
        organization=subscription.organization,
        client=actor,
        subscription=subscription,
        kind=kind,
        requirements=requirements.strip(),
        requested_end=requested_end,
        additional_service=additional_service,
        quote=submission.quote_request,
    )


@transaction.atomic
def apply(*, actor, request_id):
    from apps.subscriptions import services
    from apps.subscriptions.models import SubscriptionEvent, SubscriptionEventKind

    require("service_requests", actor)
    change = (
        ServiceChangeRequest.objects.select_for_update()
        .select_related("organization", "client")
        .get(pk=request_id)
    )
    if not can(actor, "subscriptions_approve", change) or not can(
        actor, "subscriptions_edit", change
    ):
        raise PermissionDenied
    if change.applied_at:
        return change
    from apps.leads.models import QuoteRequest

    quote = QuoteRequest.objects.select_for_update().get(pk=change.quote_id)
    if quote.status != QuoteStatus.ACCEPTED:
        raise ValidationError("The client must accept the quotation before a service is changed.")
    if quote.organization_id != change.organization_id or quote.submitted_by_id != change.client_id:
        raise ValidationError("The accepted quotation no longer belongs to this request.")
    subscription = ClientSubscription.objects.select_for_update().get(pk=change.subscription_id)
    lines = list(quote.items.filter(is_included=True))
    if not lines or any(line.quoted_amount is None for line in lines):
        raise ValidationError("Price every included line before applying this request.")
    if change.kind == "additional":
        created, _ = services.create_from_quote(
            quote=quote, actor=actor, status=SubscriptionStatus.ACTIVE
        )
        if not created:
            raise ValidationError("No new service could be activated from this quotation.")
    else:
        if subscription.status == SubscriptionStatus.CANCELLED:
            raise ValidationError("A cancelled service needs a new agreement.")
        if change.kind in {"renewal", "extension"}:
            if not change.requested_end or change.requested_end <= (
                subscription.ends_on or timezone.localdate()
            ):
                raise ValidationError("This extension no longer adds time to the current service.")
            subscription.ends_on = change.requested_end
        if change.kind == "renewal":
            if len({(line.currency, line.billing_type) for line in lines}) != 1:
                raise ValidationError("Use one currency and billing period for a renewal.")
            subscription.price = sum(line.quoted_amount for line in lines)
            subscription.currency, subscription.billing_type = (
                lines[0].currency,
                lines[0].billing_type,
            )
        if change.kind == "extra":
            scope = quote.staff_summary or change.requirements
            subscription.custom_scope += f"\nAdditional agreed work ({quote.reference}): {scope}"
        subscription.full_clean()
        subscription.save()
        if change.kind == "renewal" and subscription.status != SubscriptionStatus.ACTIVE:
            services.change_status(
                subscription=subscription,
                status=SubscriptionStatus.ACTIVE,
                actor=actor,
                note=f"Renewed under {quote.reference}.",
            )
        SubscriptionEvent.objects.create(
            subscription=subscription,
            kind=SubscriptionEventKind.SCOPE,
            actor=actor,
            body=f"{change.get_kind_display()} applied under {quote.reference}.",
            is_internal=False,
        )
    change.applied_at, change.applied_by = timezone.now(), actor
    change.save(update_fields=["applied_at", "applied_by", "updated_at"])
    notify(
        recipient=change.client,
        title="Your service request has been applied",
        body=subscription.name,
        url=reverse("organizations:service_requests"),
        category="subscription",
    )
    return change
