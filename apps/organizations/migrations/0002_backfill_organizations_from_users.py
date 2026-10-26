"""Turn each existing client's company name into a real Organization.

Until now a client company was a string on the user row. This runs while
`accounts.User.company_name` still exists — the migration that drops it
depends on this one — and converts each distinct company into an
Organization with that user as its owner.

Users who never gave a company name are left alone: they are picked up by
the onboarding step on their next sign-in.
"""

from django.db import migrations
from django.utils.text import slugify


def _unique_slug(name, taken):
    base = slugify(name)[:200] or "organization"
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"[:220]
        suffix += 1
    taken.add(candidate)
    return candidate


def create_organizations_from_company_names(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Organization = apps.get_model("organizations", "Organization")
    OrganizationMember = apps.get_model("organizations", "OrganizationMember")

    taken = set(Organization.objects.values_list("slug", flat=True))

    clients = (
        User.objects.filter(user_type="client")
        .exclude(company_name="")
        .order_by("date_joined")
    )

    for user in clients:
        if OrganizationMember.objects.filter(user_id=user.pk).exists():
            continue

        name = user.company_name.strip()
        if not name:
            continue

        # Two people from the same company share one organization rather
        # than ending up with a duplicate each.
        organization = Organization.objects.filter(name__iexact=name).first()
        if organization is None:
            organization = Organization.objects.create(
                name=name,
                slug=_unique_slug(name, taken),
                # An existing active account implies the relationship is
                # live; anything else still has to be onboarded.
                status="active" if user.status == "active" else "pending",
                status_changed_at=user.date_joined,
            )

        OrganizationMember.objects.create(
            organization=organization,
            user=user,
            # The first person from a company becomes its owner; anyone
            # later joins as a member.
            role="owner" if not OrganizationMember.objects.filter(
                organization=organization, role="owner"
            ).exists() else "member",
            status="active",
        )


def restore_company_names(apps, schema_editor):
    """Write the owner's organization name back onto the user row."""
    OrganizationMember = apps.get_model("organizations", "OrganizationMember")

    for membership in OrganizationMember.objects.select_related(
        "organization", "user"
    ).filter(status="active"):
        user = membership.user
        if not user.company_name:
            user.company_name = membership.organization.name
            user.save(update_fields=["company_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0001_initial"),
        # The backfill reads accounts.User.company_name, so it must run
        # while that column still exists.
        ("accounts", "0002_remove_user_user_type_active_idx_user_company_name_and_more"),
    ]

    operations = [
        migrations.RunPython(
            create_organizations_from_company_names,
            restore_company_names,
        ),
    ]
