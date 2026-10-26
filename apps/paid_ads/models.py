"""Daily observations, never lifetime counters or simulated advertising data."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.campaigns.models import CampaignDetail
from apps.core.models import TimeStampedModel
from apps.organizations.models import OrganizationOwnedModel

CURRENCY_VALIDATOR = RegexValidator(r"^[A-Z]{3}$", "Use a three-letter currency code.")

#: Present on every row since the table's first migration. A CSV import
#: still requires exactly these columns, so an old export keeps working
#: unmodified.
REQUIRED_MEASURES = ("spend", "impressions", "clicks", "leads", "conversions", "revenue")

#: Added for objective-aware reporting (awareness, traffic and
#: engagement campaigns are read by these, not by clicks or revenue).
#: Nullable and optional everywhere a measure is written, because most
#: providers this platform can sync today only ever report the required
#: set — an absent reach is "not reported here," never "reported as
#: zero."
OPTIONAL_MEASURES = ("reach", "link_clicks", "landing_page_views",
                     "engagements", "video_views")

MEASURES = (*REQUIRED_MEASURES, *OPTIONAL_MEASURES)


class Platform(models.TextChoices):
    GOOGLE = "google", "Google"
    META = "meta", "Meta"
    LINKEDIN = "linkedin", "LinkedIn"
    TIKTOK = "tiktok", "TikTok"
    OTHER = "other", "Other"


def validate_campaign(record):
    if record.campaign_id:
        if record.campaign.organization_id != record.organization_id:
            raise ValidationError({"campaign": "Choose a campaign belonging to this client."})
        if record.campaign.service_type != "paid_ads":
            raise ValidationError({"campaign": "Choose a Paid Ads campaign."})


class DailyAdMetric(OrganizationOwnedModel, TimeStampedModel):
    """One daily total per campaign/platform; currency is a historical snapshot."""

    date = models.DateField()
    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.PROTECT, related_name="ad_metrics"
    )
    platform = models.CharField(max_length=20, choices=Platform.choices)
    currency = models.CharField(max_length=3, validators=[CURRENCY_VALIDATOR])
    spend = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    impressions = models.PositiveBigIntegerField()
    clicks = models.PositiveBigIntegerField()
    leads = models.PositiveBigIntegerField()
    conversions = models.PositiveBigIntegerField()
    revenue = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(0)]
    )
    #: Distinct people reached, where the provider reports it — never
    #: derivable from impressions (one person can be served many
    #: impressions). Awareness campaigns are read by this, not clicks.
    reach = models.PositiveBigIntegerField(null=True, blank=True)
    #: Clicks to the destination URL specifically, as distinct from
    #: engagement clicks (likes, expands) some providers also count
    #: under a generic "clicks" total.
    link_clicks = models.PositiveBigIntegerField(null=True, blank=True)
    landing_page_views = models.PositiveBigIntegerField(null=True, blank=True)
    engagements = models.PositiveBigIntegerField(null=True, blank=True)
    video_views = models.PositiveBigIntegerField(null=True, blank=True)
    source = models.CharField(max_length=200, help_text="Report or source of this observation.")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ad_metrics_recorded",
    )
    entry_method = models.CharField(
        max_length=10,
        choices=[("manual", "Manual"), ("csv", "CSV"), ("sync", "Provider sync")],
    )

    class Meta:
        ordering = ["-date", "campaign_id", "platform"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "platform", "date"], name="ad_metric_daily_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(spend__gte=0, revenue__gte=0), name="ad_metric_money_nonnegative"
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "currency", "date"], name="ad_metric_org_date_idx"
            ),
            models.Index(
                fields=["organization", "platform", "date"], name="ad_metric_platform_idx"
            ),
        ]

    def clean(self):
        super().clean()
        validate_campaign(self)
        if self.date and self.date > timezone.localdate():
            raise ValidationError({"date": "Observed performance cannot be in the future."})

    def __str__(self):
        return f"{self.campaign_id}: {self.platform} on {self.date}"


class GoalMetric(models.TextChoices):
    SPEND = "spend", "Ad spend ceiling"
    LEADS = "leads", "Leads"
    CONVERSIONS = "conversions", "Conversions"
    REVENUE = "revenue", "Revenue"
    ROAS = "roas", "Minimum ROAS"
    CPL = "cpl", "Maximum CPL"


class PaidAdsGoal(OrganizationOwnedModel, TimeStampedModel):
    title = models.CharField(max_length=150)
    metric = models.CharField(max_length=20, choices=GoalMetric.choices)
    target = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    starts_on = models.DateField()
    ends_on = models.DateField()
    currency = models.CharField(max_length=3, validators=[CURRENCY_VALIDATOR])
    platform = models.CharField(max_length=20, choices=Platform.choices, blank=True)
    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ad_goals",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["ends_on", "pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(target__gt=0), name="ad_goal_positive"),
            models.CheckConstraint(
                condition=models.Q(ends_on__gte=models.F("starts_on")), name="ad_goal_date_order"
            ),
        ]

    def clean(self):
        super().clean()
        validate_campaign(self)
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError({"ends_on": "The end must be on or after the start."})
        if (
            self.metric in {GoalMetric.LEADS, GoalMetric.CONVERSIONS}
            and isinstance(self.target, Decimal)
            and self.target.is_finite()
            and self.target != self.target.to_integral_value()
        ):
            raise ValidationError({"target": "Use a whole-number target for counts."})

    def __str__(self):
        return self.title

    @property
    def is_ceiling(self):
        return self.metric in {GoalMetric.SPEND, GoalMetric.CPL}


class CampaignObjective(models.TextChoices):
    """What a paid promotion is bought to achieve.

    This is the vocabulary objective-aware reporting prioritizes by —
    an awareness campaign's dashboard leads with reach and CPM, a lead
    generation campaign's leads with leads and CPL. Deliberately closed
    rather than free text: a dashboard that branches on `objective in
    {...}` needs the set of values to be exactly this one.
    """

    AWARENESS = "awareness", "Awareness"
    REACH = "reach", "Reach"
    TRAFFIC = "traffic", "Traffic"
    ENGAGEMENT = "engagement", "Engagement"
    LEAD_GENERATION = "lead_generation", "Lead generation"
    SALES = "sales", "Sales"
    CONVERSIONS = "conversions", "Conversions"
    WEBSITE_VISITS = "website_visits", "Website visits"
    VIDEO_VIEWS = "video_views", "Video views"
    FOLLOWER_GROWTH = "follower_growth", "Follower growth"
    CUSTOM = "custom", "Custom"


#: Which measures the dashboard leads with for a given objective, most
#: important first — section 10's prioritization, expressed as data
#: rather than template conditionals. A key not listed here (CUSTOM, or
#: an objective left blank) falls back to a sensible general-purpose
#: order rather than raising.
OBJECTIVE_PRIORITY: dict[str, tuple[str, ...]] = {
    CampaignObjective.AWARENESS: ("spend", "reach", "impressions", "frequency", "cpm"),
    CampaignObjective.REACH: ("spend", "reach", "impressions", "frequency", "cpm"),
    CampaignObjective.TRAFFIC: ("spend", "link_clicks", "landing_page_views", "ctr", "cpc"),
    CampaignObjective.WEBSITE_VISITS: ("spend", "link_clicks", "landing_page_views", "ctr", "cpc"),
    CampaignObjective.ENGAGEMENT: ("spend", "reach", "engagements", "engagement_rate",
                                  "video_views", "cost_per_engagement"),
    CampaignObjective.FOLLOWER_GROWTH: ("spend", "reach", "engagements", "engagement_rate",
                                        "cost_per_engagement"),
    CampaignObjective.LEAD_GENERATION: ("spend", "leads", "cpl", "conversions"),
    CampaignObjective.SALES: ("spend", "conversions", "cpa", "revenue", "roas"),
    CampaignObjective.CONVERSIONS: ("spend", "conversions", "cpa", "revenue", "roas"),
    CampaignObjective.VIDEO_VIEWS: ("spend", "reach", "video_views", "cost_per_video_view",
                                    "engagements"),
}

#: Shown when no objective-specific priority applies. Covers `custom`,
#: a blank objective, or a campaign with no `PaidAdsCampaignDetail` yet.
DEFAULT_PRIORITY = ("spend", "impressions", "clicks", "leads", "conversions", "revenue")


def priority_for(objective: str) -> tuple[str, ...]:
    return OBJECTIVE_PRIORITY.get(objective, DEFAULT_PRIORITY)


class PaidAdsCampaignDetail(CampaignDetail):
    """Platform and objective for one paid promotion.

    The two fields the generic `Campaign` deliberately does not carry —
    see its module docstring. `platform` is what the client sees as a
    badge ("Meta", "Google Ads"); `objective` is what decides which KPIs
    this campaign's reporting leads with.
    """

    platform = models.CharField(_("platform"), max_length=20,
                                choices=Platform.choices,
                                help_text=_("Where this promotion runs. A "
                                           "campaign spanning more than one "
                                           "platform is recorded as "
                                           "separate campaigns — this is "
                                           "the client example in the "
                                           "brief's own numbered list."))
    objective = models.CharField(_("objective"), max_length=20,
                                 choices=CampaignObjective.choices,
                                 blank=True,
                                 help_text=_("Decides which performance "
                                            "numbers this campaign's "
                                            "dashboard leads with."))

    class Meta:
        verbose_name = _("paid ads campaign detail")
        verbose_name_plural = _("paid ads campaign details")

    def __str__(self) -> str:
        return f"{self.campaign_id}: {self.get_platform_display()}"
