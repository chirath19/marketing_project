"""Create the Permission rows the catalogue declares.

Idempotent: safe to run on every deploy. Permissions that have been
removed from the catalogue are reported but not deleted by default —
dropping one silently revokes it from every role that holds it, which is
not something a deploy should do without being asked.
"""

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.permissions.catalogue import (
    APP_LABEL,
    CONTENT_TYPE_MODEL,
    MODULES,
    codename,
    label_for,
)


def sync_permissions(*, prune: bool = False) -> dict[str, int]:
    """Bring the Permission table in line with the catalogue."""
    content_type, _created = ContentType.objects.get_or_create(
        app_label=APP_LABEL, model=CONTENT_TYPE_MODEL,
    )

    wanted = {
        codename(module.key, action): label_for(module.key, action)
        for module in MODULES
        for action in module.actions
    }

    existing = {
        permission.codename: permission
        for permission in Permission.objects.filter(content_type=content_type)
    }

    created = updated = 0
    for name, label in wanted.items():
        permission = existing.get(name)
        if permission is None:
            Permission.objects.create(
                codename=name, name=label, content_type=content_type,
            )
            created += 1
        elif permission.name != label:
            permission.name = label
            permission.save(update_fields=["name"])
            updated += 1

    stale = sorted(set(existing) - set(wanted))
    removed = 0
    if prune and stale:
        removed, _ = Permission.objects.filter(
            content_type=content_type, codename__in=stale,
        ).delete()

    return {"created": created, "updated": updated,
            "stale": len(stale), "removed": removed, "total": len(wanted)}


class Command(BaseCommand):
    help = "Create or update the platform's permissions from the catalogue."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--prune", action="store_true",
            help="Also delete permissions no longer in the catalogue. This "
                 "revokes them from every role that holds them.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        result = sync_permissions(prune=options["prune"])

        self.stdout.write(
            f"{result['total']} permissions in the catalogue: "
            f"{result['created']} created, {result['updated']} relabelled."
        )
        if result["stale"]:
            if result["removed"]:
                self.stdout.write(self.style.WARNING(
                    f"{result['removed']} stale permission(s) deleted."))
            else:
                self.stdout.write(self.style.WARNING(
                    f"{result['stale']} permission(s) are no longer in the "
                    "catalogue. Re-run with --prune to remove them."))
        self.stdout.write(self.style.SUCCESS("Permissions are in sync."))
