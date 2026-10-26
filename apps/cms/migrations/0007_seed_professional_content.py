"""Replace the starter copy with content the agency can actually launch on.

Everything written here is editable in the CMS; this migration decides
what a fresh install says on day one, not what it says forever.

Two rules governed the writing:

**Nothing is invented.** No client names, no case-study figures, no
awards, no years in business, no headcount, no testimonials. Where a
claim would need a fact nobody has given us, the copy describes how the
agency works instead — which is true, useful, and does not go stale.

**Nothing is promised that the platform cannot keep.** There is no
outbound email in this version, so no page says a confirmation is
coming. Reply times live in a settings field that ships empty, because a
promise on the page is a promise somebody has to keep.

The migration is written to be re-runnable in spirit: it updates the
pages the first seed created rather than assuming an untouched database,
and it leaves anything an editor has since added alone.
"""

from django.db import migrations
from django.utils import timezone


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

HOME_SECTIONS = [
    dict(
        section_type="hero", order=10, tone="navy",
        eyebrow="Digital marketing agency",
        heading="Marketing built around measurable growth.",
        subheading=(
            "We combine strategy, search, advertising, content and analytics "
            "to help businesses attract the right customers — and to show, "
            "in plain numbers, what each part of that is doing."
        ),
        cta_label="Explore services", cta_url="/services/",
        secondary_cta_label="Request a quote", secondary_cta_url="/quote/",
    ),
    dict(
        section_type="feature_grid", order=20, tone="light", columns=3,
        eyebrow="What we do",
        heading="Six disciplines, one plan",
        subheading=(
            "Take a single service or combine several into one programme. "
            "Whatever the mix, it reports into the same place."
        ),
        items=[
            ("Search", "Technical SEO, local search, on-page work and content "
                       "built around the queries your customers actually use."),
            ("Paid advertising", "Google, Meta and LinkedIn campaigns managed "
                                 "against cost per customer rather than clicks."),
            ("Social media", "A consistent publishing rhythm, community "
                             "management and creator partnerships."),
            ("Email marketing", "Newsletters, automated flows and campaign "
                                "analysis for your own audience."),
            ("Analytics", "Tracking that works, conversion measurement you can "
                          "trust, and reporting you can read."),
            ("Strategy", "Channel planning, budget allocation and quarterly "
                         "performance reviews."),
        ],
    ),
    dict(
        section_type="rich_text", order=30, tone="mist",
        eyebrow="How we think",
        heading="Strategy before activity",
        body=(
            "It is easy to be busy in marketing. Posts go out, budgets get "
            "spent, reports get written, and nobody can say which part of it "
            "moved the business.\n\n"
            "We start the other way round: what the business needs, which "
            "channels can realistically deliver it, and how we will know. "
            "Only then do we decide what to run. It is a slower start and a "
            "considerably shorter route."
        ),
    ),
    dict(
        section_type="feature_grid", order=40, tone="light", columns=3,
        eyebrow="Why work with us",
        heading="What you can expect",
        items=[
            ("Strategy before activity", "A plan that says what we are doing "
                                         "and why, agreed before anything runs."),
            ("Clear reporting", "Numbers in context, in language you do not "
                                "need a marketing background to read."),
            ("Flexible services", "Start with one service, add others when "
                                  "they earn their place. Nothing is bundled "
                                  "to pad an invoice."),
            ("Transparent collaboration", "You see the work in progress, not a "
                                          "polished summary a month later."),
            ("Data-driven decisions", "Changes are argued from measurement. "
                                      "Where the data is thin, we say so."),
            ("A dedicated workspace", "Your own client area for services, "
                                      "campaigns, reports and approvals."),
        ],
    ),
    dict(
        section_type="feature_grid", order=50, tone="mist", columns=3,
        eyebrow="How we work",
        heading="From first conversation to steady improvement",
        subheading=(
            "The same six steps whichever services you take. The detail "
            "changes; the order does not."
        ),
        items=[
            ("1. Discovery", "We learn the business, the margins, the customer "
                             "and what has already been tried."),
            ("2. Review", "An audit of what exists today — the site, the "
                          "accounts, the tracking, the competition."),
            ("3. Strategy", "Channels, budget split, targets and the "
                            "measurement that will prove them."),
            ("4. Implementation", "The work itself, scheduled and visible to "
                                  "you as it happens."),
            ("5. Measurement", "Results against the targets we agreed, "
                               "reported on a predictable rhythm."),
            ("6. Optimisation", "What worked gets more budget. What did not "
                                "gets changed or stopped."),
        ],
    ),
    dict(
        section_type="rich_text", order=60, tone="light",
        eyebrow="Your client workspace",
        heading="You see what we see",
        body=(
            "Every client gets an account on this platform. Your active "
            "services, the campaigns running under them, the reports as they "
            "are published and anything waiting on your decision all live "
            "there.\n\n"
            "It replaces the monthly slide deck and the chase for an update. "
            "When something needs approving, it appears in your workspace "
            "and waits for you — nothing moves ahead of your sign-off."
        ),
    ),
    dict(
        section_type="feature_grid", order=70, tone="mist", columns=3,
        eyebrow="Who we work with",
        heading="Built for businesses that need marketing to pay for itself",
        subheading=(
            "The channels differ by sector. The discipline does not."
        ),
        items=[
            ("Startups", "Finding the first repeatable channel without "
                         "burning the runway proving it."),
            ("Small and medium businesses", "Competing on relevance and "
                                            "service against larger budgets."),
            ("Established businesses", "Modernising measurement and getting "
                                       "more from spend that already exists."),
            ("E-commerce", "Product-level economics, feed quality and the "
                           "difference between revenue and margin."),
            ("Professional services", "Fewer, better enquiries — measured on "
                                      "cost per qualified lead, not volume."),
            ("Growing brands", "Holding a consistent brand while the channel "
                               "mix expands underneath it."),
        ],
    ),
    dict(
        section_type="testimonials", order=80, tone="light",
        eyebrow="Clients", heading="In their words",
    ),
    dict(
        section_type="faq", order=90, tone="mist",
        eyebrow="Questions",
        heading="The things people ask before they get in touch",
    ),
    dict(
        section_type="cta_band", order=100, tone="navy",
        heading="Tell us what you are trying to achieve",
        subheading=(
            "Share your goals and we will come back with a scope, a price "
            "and a realistic view of what to expect."
        ),
        cta_label="Request a quote", cta_url="/quote/",
        secondary_cta_label="Send an enquiry", secondary_cta_url="/contact/",
    ),
]


# ---------------------------------------------------------------------------
# About
# ---------------------------------------------------------------------------

ABOUT_SECTIONS = [
    dict(
        section_type="hero", order=10, tone="mist",
        eyebrow="About us",
        heading="A marketing partner that argues from evidence",
        subheading=(
            "We are a full-service digital marketing agency. We plan, run "
            "and measure marketing for businesses that need it to produce "
            "something countable."
        ),
    ),
    dict(
        section_type="rich_text", order=20, tone="light",
        eyebrow="Who we are",
        heading="Specialists, not generalists with a template",
        body=(
            "Search, paid media, social, email and analytics are different "
            "crafts. We staff them that way: the person optimising your ad "
            "account is not the person writing your content calendar, and "
            "neither of them is guessing.\n\n"
            "What holds it together is a single plan and a single set of "
            "numbers. You get specialist work without having to coordinate "
            "five suppliers who each report on something different."
        ),
    ),
    dict(
        section_type="feature_grid", order=30, tone="mist", columns=3,
        eyebrow="What we believe",
        heading="The principles we work to",
        items=[
            ("Clarity", "If a report needs explaining before it makes sense, "
                        "it is not finished."),
            ("Accountability", "We agree what good looks like in advance and "
                               "report against it, including when it is "
                               "short."),
            ("Practical strategy", "A plan you cannot resource is not a "
                                   "strategy. We scope to what is actually "
                                   "available."),
            ("Measurable outcomes", "Enquiries, sales and cost per customer. "
                                    "Impressions are diagnostics, not results."),
            ("Continuous improvement", "Marketing is iterative. The first "
                                       "version is a starting position, not "
                                       "a verdict."),
            ("Long-term partnerships", "Compounding results need continuity. "
                                       "We are set up for the long engagement."),
        ],
    ),
    dict(
        section_type="rich_text", order=40, tone="light",
        eyebrow="How we work with you",
        heading="Close enough to be useful",
        body=(
            "You get a named point of contact and direct access to the "
            "specialists doing the work. Questions do not queue behind an "
            "account manager who has to go and ask.\n\n"
            "Work in progress is visible in your client workspace as it "
            "happens, and anything that needs your decision waits there "
            "until you make it. We would rather show you an unfinished "
            "thing early than a finished thing you would have changed."
        ),
    ),
    dict(
        section_type="rich_text", order=50, tone="mist",
        eyebrow="Our mission",
        heading="Make marketing spend defensible",
        body=(
            "Too many businesses cannot say what their marketing returns. "
            "Not because the answer is unknowable, but because nobody set "
            "it up to be measured.\n\n"
            "Our work is to close that gap: run marketing that performs, and "
            "make its performance legible to the people paying for it."
        ),
    ),
    dict(
        section_type="team", order=60, tone="light",
        eyebrow="The team",
        heading="The people on your account",
    ),
    dict(
        section_type="cta_band", order=70, tone="navy",
        heading="Work with us",
        subheading="Tell us where you are now and where you need to get to.",
        cta_label="Request a quote", cta_url="/quote/",
        secondary_cta_label="Send an enquiry", secondary_cta_url="/contact/",
    ),
]


# ---------------------------------------------------------------------------
# Services introduction — rendered above the catalogue grid
# ---------------------------------------------------------------------------

SERVICES_SECTIONS = [
    dict(
        section_type="hero", order=10, tone="mist",
        eyebrow="Services",
        heading="Take one service, or build a programme",
        subheading=(
            "Every service below is sold on its own and priced on its own. "
            "Combine them when the plan calls for it — there is no bundle "
            "you have to buy into, and nothing here depends on you taking "
            "something else."
        ),
        cta_label="Request a quote", cta_url="/quote/",
        secondary_cta_label="Talk to our team", secondary_cta_url="/contact/",
    ),
    dict(
        section_type="rich_text", order=20, tone="light",
        eyebrow="Not sure where to start",
        heading="A short way to narrow it down",
        body=(
            "**If nobody can find you**, start with search. Technical SEO "
            "fixes what is holding the site back; content and local search "
            "build on it. It is the slowest channel to start and the "
            "cheapest to sustain.\n\n"
            "**If you need enquiries this quarter**, start with paid "
            "advertising. It buys attention immediately, which makes it the "
            "fastest way to learn what your market responds to — and the "
            "fastest way to waste money without measurement in place.\n\n"
            "**If you already have traffic but few customers**, the problem "
            "is usually measurement or conversion rather than volume. Begin "
            "with analytics and tracking, and you will stop guessing which "
            "of the two it is.\n\n"
            "**If you have an audience you are not using**, email is the "
            "cheapest channel you own. Flows and newsletters earn from "
            "people who already know you.\n\n"
            "Still unsure? Describe the business and the goal, and we will "
            "recommend a starting point — including when the honest answer "
            "is that you do not need us yet."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Privacy — structural and honest, with no legal guarantees claimed
# ---------------------------------------------------------------------------

PRIVACY_SECTIONS = [
    dict(
        section_type="hero", order=10, tone="mist",
        eyebrow="Legal",
        heading="Privacy and data",
        subheading=(
            "What this site collects, why, and what you can ask us to do "
            "about it."
        ),
    ),
    dict(
        section_type="rich_text", order=20, tone="light",
        heading="What we collect when you browse",
        body=(
            "Visiting the public pages of this site does not require an "
            "account and does not ask you for anything.\n\n"
            "Our own server keeps standard request logs for security and "
            "diagnostics. Where we record that an enquiry came from a "
            "particular connection, we store a one-way fingerprint of the "
            "address rather than the address itself — enough to recognise "
            "a flood of automated submissions, not enough to reconstruct "
            "who was browsing."
        ),
    ),
    dict(
        section_type="rich_text", order=30, tone="mist",
        heading="Enquiries and quote requests",
        body=(
            "When you send an enquiry or a quote request, we store what you "
            "submitted: your name, the contact details you gave, the "
            "services you selected and your message. It is saved in our own "
            "database and shown to the staff handling enquiries.\n\n"
            "We use it to respond to you and to keep a record of the "
            "conversation. We do not sell it, and we do not add you to a "
            "marketing list because you contacted us."
        ),
    ),
    dict(
        section_type="rich_text", order=40, tone="light",
        heading="Client accounts",
        body=(
            "If you register for a client account, we store your name, email "
            "address, the organisation you belong to and the contact details "
            "you choose to add. Staff can see the accounts belonging to the "
            "clients they are assigned to.\n\n"
            "Work we deliver for you — campaigns, reports, approvals and "
            "messages — is held against your organisation and is visible to "
            "the people in it, not to other clients."
        ),
    ),
    dict(
        section_type="rich_text", order=50, tone="mist",
        heading="Cookies and tracking",
        body=(
            "This site sets only the cookies it needs to work: one to keep "
            "your session when you sign in, and one to protect forms against "
            "cross-site request forgery. Your quote selection is held in the "
            "same session so it survives moving between pages.\n\n"
            "We do not currently run third-party advertising or analytics "
            "tracking on this site. If that changes, we will ask for your "
            "consent before any such tracking loads, and this page will say "
            "what it is and who operates it.\n\n"
            "Marketing measurement we set up **for our clients** runs on "
            "their own websites under their own privacy notices, not here."
        ),
    ),
    dict(
        section_type="rich_text", order=60, tone="light",
        heading="Keeping and removing your information",
        body=(
            "We keep enquiries and client records for as long as we have a "
            "working relationship or a reason to, and remove them when we do "
            "not.\n\n"
            "You can ask us what we hold about you, ask for it to be "
            "corrected, or ask us to delete it. Get in touch and we will "
            "handle it.\n\n"
            "This page describes our practice. It is not legal advice, and "
            "it does not by itself make us compliant with any particular "
            "regulation — where a specific framework applies to you, we are "
            "happy to go through the detail."
        ),
    ),
    dict(
        section_type="contact_details", order=70, tone="mist",
        heading="Questions about any of this",
        subheading="Ask us directly.",
    ),
]


# ---------------------------------------------------------------------------
# Questions and answers — every one answered against what is built
# ---------------------------------------------------------------------------

FAQS = [
    ("What services do you offer?",
     "Search engine optimisation including technical and local SEO, paid "
     "advertising across Google, Meta and LinkedIn, social media management "
     "and creator partnerships, email marketing, analytics and conversion "
     "tracking, and the strategy work that decides which of those you "
     "actually need. The full list with prices is in the service catalogue."),

    ("Can I use only one marketing service?",
     "Yes. Every service is scoped and priced on its own, and none of them "
     "requires another. Plenty of clients start with a single audit or one "
     "ad account and never take anything else."),

    ("Can I add more services later?",
     "Yes, and that is the usual pattern. Services are added to your account "
     "individually, so a new one starts when it is agreed rather than at a "
     "contract renewal. Your workspace updates to show it."),

    ("How are campaigns reported?",
     "Reporting is published to your client workspace rather than emailed as "
     "a deck. You see what is running, what it has cost and what it has "
     "returned, against the targets agreed at the start. The reporting "
     "rhythm is set per service and confirmed in your scope."),

    ("Will I get my own client dashboard?",
     "Yes. Every client organisation gets a workspace on this platform. It "
     "shows your active services, campaigns, reports, approvals and messages "
     "with your account team. It is included — there is no separate charge "
     "for access."),

    ("Can several people from my company use the account?",
     "Yes. A client account belongs to your organisation, not to one person, "
     "and colleagues can be added as members of it. Everyone in your "
     "organisation sees your organisation's work and nobody else's."),

    ("How do approvals work?",
     "When something needs your decision before work continues — a campaign "
     "going live, a piece of content, a budget change — it appears in your "
     "workspace as an approval. You approve it, reject it or ask for "
     "changes, and the decision is recorded against the work."),

    ("Can services be paused or changed?",
     "Yes. Scope can be adjusted, and monthly services can be paused or "
     "stopped by agreement. We will tell you honestly what pausing costs "
     "you — with search in particular, stopping and restarting is more "
     "expensive than it looks."),

    ("How is pricing determined?",
     "Catalogue prices are the standard scope for each service. What you pay "
     "depends on which services you take and how much of them you need — "
     "the size of the site, the number of markets, how much is already in "
     "place. Anything outside a standard scope is quoted on the work."),

    ("What do you need from us to get started?",
     "Access to what already exists — your website, ad accounts, analytics "
     "and anything else relevant — plus an honest account of what you have "
     "tried and what you are measured on internally. We handle the setup "
     "from there."),

    ("Will you contact me automatically after I submit a form?",
     "No automated email or message is sent. Your enquiry is stored and "
     "goes straight to the team handling enquiries, and a person replies "
     "using the contact details you gave us."),
]


def seed(apps, schema_editor):
    Page = apps.get_model("cms", "Page")
    PageSection = apps.get_model("cms", "PageSection")
    SectionItem = apps.get_model("cms", "SectionItem")
    NavigationItem = apps.get_model("cms", "NavigationItem")
    FAQ = apps.get_model("cms", "FAQ")
    SiteSettings = apps.get_model("cms", "SiteSettings")

    now = timezone.now()

    def build(page, specs):
        """Replace a page's sections with the ones given.

        Replace rather than merge: these pages are the seed's own, and a
        half-updated page reading as two drafts spliced together is worse
        than either version.
        """
        PageSection.objects.filter(page=page).delete()
        for spec in specs:
            items = spec.pop("items", None)
            section = PageSection.objects.create(
                page=page, created_at=now, updated_at=now, **spec
            )
            for order, (label, body) in enumerate(items or [], start=1):
                SectionItem.objects.create(
                    section=section, label=label, body=body,
                    order=order * 10, created_at=now, updated_at=now,
                )

    def page_for(kind, *, slug, title, meta_title="", meta_description=""):
        """The page of this kind, found by kind then slug, or created.

        Matched on kind only for the named kinds, which are unique by
        definition. "standard" is not one of them: matching on it would
        grab whatever standard page happened to be first and overwrite
        an editor's work.
        """
        page = (Page.objects.filter(kind=kind).first()
                if kind != "standard" else None)
        if page is None:
            page = Page.objects.filter(slug=slug).first()
        if page is None:
            page = Page.objects.create(
                title=title, slug=slug, kind=kind, status="published",
                published_at=now, created_at=now, updated_at=now,
            )
        page.title = title
        page.meta_title = meta_title
        page.meta_description = meta_description
        if page.status != "published":
            page.status = "published"
            page.published_at = page.published_at or now
        page.updated_at = now
        page.save()
        return page

    home = page_for(
        "home", slug="home", title="Home",
        meta_title="Digital marketing agency built around measurable growth",
        meta_description=(
            "Search, paid advertising, social, email and analytics — planned "
            "together and reported in one place. Take one service or build a "
            "programme."
        ),
    )
    build(home, [dict(spec) for spec in HOME_SECTIONS])

    about = page_for(
        "about", slug="about", title="About",
        meta_title="About us — how we plan, run and measure marketing",
        meta_description=(
            "A full-service digital marketing agency that argues from "
            "evidence. Our principles, our approach and how we work with "
            "clients."
        ),
    )
    build(about, [dict(spec) for spec in ABOUT_SECTIONS])

    # Slug "services", which the catalogue route claims first — so this
    # page is never reachable on its own and cannot compete with the
    # catalogue for the same search result. It exists to make the
    # catalogue's own heading and intro editable.
    services = page_for(
        "services", slug="services", title="Services",
        meta_title="Digital marketing services and pricing",
        meta_description=(
            "SEO, Google and Meta ads, LinkedIn, social media, email "
            "marketing, analytics and strategy. Scoped and priced "
            "individually."
        ),
    )
    build(services, [dict(spec) for spec in SERVICES_SECTIONS])

    contact = page_for(
        "contact", slug="contact", title="Contact",
        meta_title="Contact us — tell us what you are working on",
        meta_description=(
            "Send an enquiry about SEO, paid advertising, social, email or "
            "analytics. Every message reaches our team directly."
        ),
    )
    build(contact, [
        dict(
            section_type="hero", order=10, tone="mist",
            eyebrow="Contact",
            heading="Tell us what you are working on",
            subheading=(
                "Your goals, your website, what is not working, or which "
                "services you are weighing up. The more you tell us, the "
                "more useful the reply."
            ),
        ),
        dict(
            section_type="contact_form", order=20, tone="light",
            heading="Send us an enquiry",
            subheading=(
                "Every submission is read by our team. Nothing here is "
                "automated."
            ),
        ),
        dict(
            section_type="contact_details", order=30, tone="mist",
            heading="Or reach us directly",
            subheading="However you prefer to start the conversation.",
        ),
    ])

    privacy = page_for(
        "standard", slug="privacy", title="Privacy and data",
        meta_title="Privacy and data",
        meta_description=(
            "What this site collects, why we collect it, and what you can "
            "ask us to do about it."
        ),
    )
    build(privacy, [dict(spec) for spec in PRIVACY_SECTIONS])

    # --- questions ---------------------------------------------------------
    # Only seeded into an untouched list: an agency that has already
    # curated its own questions should not have ours pushed back on top.
    if FAQ.objects.count() <= 2:
        FAQ.objects.all().delete()
        for order, (question, answer) in enumerate(FAQS, start=1):
            FAQ.objects.create(question=question, answer=answer,
                               order=order * 10, is_visible=True,
                               created_at=now, updated_at=now)

    # --- navigation --------------------------------------------------------
    NavigationItem.objects.all().delete()
    nav = [
        # label, placement, order, page, url, is_cta
        ("Services", "header", 10, None, "/services/", False),
        ("About", "header", 20, about, "", False),
        ("Blog", "header", 30, None, "/blog/", False),
        ("Contact", "header", 40, contact, "", False),
        ("Request a quote", "header", 50, None, "/quote/", True),

        ("About us", "footer_primary", 10, about, "", False),
        ("Blog", "footer_primary", 20, None, "/blog/", False),
        ("Contact", "footer_primary", 30, contact, "", False),
        ("Client sign in", "footer_primary", 40, None, "/accounts/login/", False),

        ("All services", "footer_secondary", 10, None, "/services/", False),
        ("Search and SEO", "footer_secondary", 20, None,
         "/services/category/search/", False),
        ("Paid advertising", "footer_secondary", 30, None,
         "/services/category/paid/", False),
        ("Social media", "footer_secondary", 40, None,
         "/services/category/social/", False),
        ("Email marketing", "footer_secondary", 50, None,
         "/services/category/email/", False),
        ("Analytics", "footer_secondary", 60, None,
         "/services/category/analytics/", False),

        ("Privacy and data", "legal", 10, privacy, "", False),
        ("Cookies and tracking", "legal", 20, None, "/privacy/#cookies-and-tracking", False),
    ]
    for label, placement, order, page, url, is_cta in nav:
        NavigationItem.objects.create(
            label=label, placement=placement, order=order,
            page=page, url=url, is_cta=is_cta, is_visible=True,
            created_at=now, updated_at=now,
        )

    # --- settings ----------------------------------------------------------
    settings_row = SiteSettings.objects.first()
    if settings_row is not None:
        settings_row.tagline = (
            "Strategy, search, advertising, content and analytics — planned "
            "together and measured in one place."
        )
        settings_row.default_meta_title = (
            "Heliograph — digital marketing built around measurable growth"
        )
        settings_row.default_meta_description = (
            "A full-service digital marketing agency. Take one service or "
            "build a programme, and track every result in your own client "
            "workspace."
        )
        settings_row.footer_note = (
            "Enquiries are handled by people, not autoresponders."
        )
        settings_row.updated_at = now
        settings_row.save()


def unseed(apps, schema_editor):
    """Intentionally a no-op.

    The previous copy is in the earlier migration's source, not in the
    database, so there is nothing faithful to restore. Deleting the pages
    would take an editor's later work with them.
    """


class Migration(migrations.Migration):

    dependencies = [("cms", "0006_content_fields")]

    operations = [migrations.RunPython(seed, unseed)]
