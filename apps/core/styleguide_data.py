"""Sample records for the styleguide.

Plain dataclasses, not model instances. The business components read
attributes off whatever they are given, so the design system can be built
and reviewed before the domain models exist — and the styleguide keeps
working when they arrive.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    name: str
    category: str
    summary: str
    price_display: str
    billing_period: str
    slug: str = ""
    inclusions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Client:
    name: str
    industry: str
    status: str
    owner: str
    active_services: int
    monthly_value: str


@dataclass(frozen=True)
class Campaign:
    name: str
    module_label: str
    status: str
    spend_display: str
    result_summary: str
    owner: str = ""
    start_date: str = ""


@dataclass(frozen=True)
class Lead:
    name: str
    company: str
    email: str
    source: str
    status: str
    summary: str
    value_display: str
    created_at: str


@dataclass(frozen=True)
class Approval:
    title: str
    module_label: str
    summary: str
    status: str
    requested_by: str = ""
    due_date: str = ""


@dataclass(frozen=True)
class Report:
    title: str
    module_label: str
    period_label: str
    summary: str
    generated_at: str
    format: str = "PDF"


@dataclass(frozen=True)
class Activity:
    title: str
    module_label: str
    timesince: str
    href: str = ""


@dataclass(frozen=True)
class Notification:
    title: str
    body: str
    created_at: str
    is_read: bool
    severity: str = "info"
    link: str = ""


@dataclass(frozen=True)
class InboxMessage:
    sender_name: str
    sender_org: str
    subject: str
    preview: str
    received_at: str
    is_read: bool
    kind_label: str
    has_attachments: bool = False


@dataclass(frozen=True)
class Page:
    """Stands in for a Django Page object so the pager can be shown."""

    number: int
    paginator: object
    start_index_value: int
    end_index_value: int

    def has_previous(self) -> bool:
        return self.number > 1

    def has_next(self) -> bool:
        return self.number < self.paginator.num_pages

    def previous_page_number(self) -> int:
        return self.number - 1

    def next_page_number(self) -> int:
        return self.number + 1

    def start_index(self) -> int:
        return self.start_index_value

    def end_index(self) -> int:
        return self.end_index_value


@dataclass(frozen=True)
class Paginator:
    num_pages: int
    count: int


SERVICES = [
    Service(
        name="SEO growth retainer", category="Search",
        summary="Monthly content, on-page work and link building to climb the results page.",
        price_display="$2,400", billing_period="per month", slug="seo-growth",
        inclusions=("Monthly content plan", "On-page optimisation",
                    "Link building outreach", "Monthly reporting"),
    ),
    Service(
        name="Technical SEO audit", category="Search",
        summary="A full review of speed, structure and indexing, with a fix list ranked by impact.",
        price_display="$1,500", billing_period="one time", slug="seo-audit",
        inclusions=("Crawl and index review", "Core Web Vitals", "Prioritised fix list"),
    ),
    Service(
        name="Google Ads management", category="Paid",
        summary="Search and Shopping campaigns managed against cost per customer.",
        price_display="$1,800", billing_period="per month", slug="google-ads",
        inclusions=("Campaign build", "Weekly optimisation", "Creative testing"),
    ),
]

CLIENTS = [
    Client(name="Northwind Supply", industry="B2B wholesale", status="active",
           owner="Amara Silva", active_services=4, monthly_value="$8,400"),
    Client(name="Atlas Fitness", industry="Health and fitness", status="pending",
           owner="Dilshan Perera", active_services=1, monthly_value="$1,600"),
]

CAMPAIGNS = [
    Campaign(name="Brand search", module_label="Paid ads", status="live",
             spend_display="$6,100", result_summary="1,420 clicks, 5.6x ROAS",
             owner="Amara Silva"),
    Campaign(name="Industry link outreach", module_label="SEO", status="live",
             spend_display="$2,400", result_summary="61 links won"),
    Campaign(name="Spring video test", module_label="Paid ads", status="paused",
             spend_display="$2,900", result_summary="Waiting on your approval"),
    Campaign(name="Schema markup rollout", module_label="SEO", status="planned",
             spend_display="$1,200", result_summary="Starts Jun 2", start_date="2 Jun"),
    Campaign(name="Product page speed fixes", module_label="SEO", status="done",
             spend_display="—", result_summary="LCP 4.1s to 1.9s"),
]

LEADS = [
    Lead(name="Priya Raman", company="Vantage Interiors",
         email="priya@vantage.example", source="Quote form", status="pending",
         summary="Wants help with search and paid ads before a spring launch.",
         value_display="$4,200", created_at="2 hours ago"),
]

APPROVALS = [
    Approval(title="Spring video test", module_label="Paid ads",
             summary="$2,900 budget", status="pending",
             requested_by="Amara Silva", due_date="Thursday"),
    Approval(title="April newsletter draft", module_label="Email",
             summary="ready to send", status="pending", requested_by="Dilshan Perera"),
    Approval(title="Creator brief, round 2", module_label="Social media",
             summary="three creators shortlisted", status="pending"),
]

REPORTS = [
    Report(title="April performance summary", module_label="All services",
           period_label="1 – 30 April", generated_at="1 May",
           summary="Leads, spend and revenue across search, ads, social and email."),
]

ACTIVITY = [
    Activity(title="Welcome flow reached 31% conversion", module_label="Email",
             timesince="2 hours ago"),
    Activity(title="61st backlink won", module_label="SEO", timesince="yesterday"),
    Activity(title="Retargeting ROAS up to 4.9x", module_label="Paid ads",
             timesince="2 days ago"),
    Activity(title="12 posts scheduled for May", module_label="Social media",
             timesince="3 days ago"),
]

NOTIFICATIONS = [
    Notification(title="Spring video test needs your approval",
                 body="Paid ads, $2,900 budget. Requested by Amara Silva.",
                 created_at="10 minutes ago", is_read=False, severity="pending"),
    Notification(title="April report is ready",
                 body="Your monthly summary across all services.",
                 created_at="yesterday", is_read=True),
]

INBOX = [
    InboxMessage(sender_name="Priya Raman", sender_org="Vantage Interiors",
                 subject="Quote request: search and paid ads",
                 preview="We are launching a new range in spring and want to be visible…",
                 received_at="2h", is_read=False, kind_label="Quote request",
                 has_attachments=True),
    InboxMessage(sender_name="Tom Alder", sender_org="Northwind Supply",
                 subject="Can we shift budget to Shopping?",
                 preview="Search is performing but Shopping looks like the better bet…",
                 received_at="yesterday", is_read=True, kind_label="Client message"),
]

CAMPAIGN_COLUMNS = [
    {"label": "Campaign"},
    {"label": "Service"},
    {"label": "Status"},
    {"label": "Spend", "align": "right"},
    {"label": "Result"},
]

FILTER_TABS = [
    {"key": "all", "label": "All", "href": "?status=all", "count": 14},
    {"key": "live", "label": "Live", "href": "?status=live", "count": 8},
    {"key": "paused", "label": "Paused", "href": "?status=paused", "count": 1},
    {"key": "planned", "label": "Planned", "href": "?status=planned", "count": 3},
    {"key": "done", "label": "Done", "href": "?status=done", "count": 2},
]

BILLING_OPTIONS = [("monthly", "Per month"), ("one_time", "One time")]

BREADCRUMBS = [
    {"label": "Dashboard", "href": "/"},
    {"label": "Campaigns", "href": "/campaigns/"},
]


def demo_page() -> Page:
    paginator = Paginator(num_pages=12, count=287)
    return Page(number=4, paginator=paginator, start_index_value=76, end_index_value=100)
