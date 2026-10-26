from django.apps import AppConfig


class SeoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.seo"
    label = "seo"
    verbose_name = "SEO"

    def ready(self) -> None:
        """Declare the SEO campaign type, with the fields it attaches.

        Registered here rather than in `apps.campaigns` so the dependency
        points the right way: SEO knows about campaigns, campaigns know
        nothing about SEO. That is what makes this a service module
        extending the core rather than the core growing a special case.
        """
        from apps.campaigns.registry import CampaignType, register

        register(CampaignType(
            key="seo",
            label="Search",
            goal_label="Target positions",
            detail_model="apps.seo.models.SeoCampaignDetail",
            description="Technical work, content and links against the "
                        "terms that bring customers.",
        ))
