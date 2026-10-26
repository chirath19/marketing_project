from django.apps import AppConfig


class TrackingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tracking"
    label = "tracking"
    verbose_name = "Agency Website Tracking"

    def ready(self) -> None:
        """Subscribe to the facts this app reports on.

        The import alone registers the `@subscribe(...)` handlers in
        `apps.tracking.services` — see that module for which events and
        why. Importing here, rather than at module load time, is what
        keeps this a one-directional dependency: `apps.leads` and
        `apps.accounts` publish without knowing this app exists.
        """
        from apps.tracking import services  # noqa: F401
