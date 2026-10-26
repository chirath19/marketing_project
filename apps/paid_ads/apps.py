from django.apps import AppConfig


class PaidAdsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.paid_ads"
    label = "paid_ads"
    verbose_name = "Paid Ads"

    def ready(self) -> None:
        """Declare the Paid Ads campaign type, with its platform/objective
        fields.

        Registered here rather than in `apps.campaigns`, the same
        direction `apps.seo` registers in: paid ads knows about
        campaigns, campaigns know nothing about paid ads.
        """
        from apps.campaigns.registry import CampaignType, register

        register(CampaignType(
            key="paid_ads",
            label="Paid advertising",
            goal_label="Cost per customer",
            detail_model="apps.paid_ads.models.PaidAdsCampaignDetail",
            detail_form="apps.paid_ads.forms.PaidAdsCampaignDetailForm",
            description="Campaigns on Google, Meta and LinkedIn, run "
                        "against a budget.",
        ))
