"""Four articles, so the blog launches with something worth reading.

Four and not forty. A blog seeded with a pile of thin, interchangeable
posts damages the thing it is meant to support: it tells a reader the
agency publishes for the sake of publishing. Each of these answers a
question a prospective client actually asks, and each is written to be
useful to somebody who never becomes a client.

They are ordinary database rows. The agency edits, unpublishes or
deletes any of them in the dashboard without touching code.

Nothing here claims a result, names a client or cites a figure we cannot
stand behind.
"""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone


CATEGORIES = [
    ("Strategy", "strategy", 10,
     "Choosing channels, setting budgets and deciding what to do first."),
    ("Measurement", "measurement", 20,
     "Tracking, attribution and reading marketing numbers honestly."),
    ("Search", "search", 30,
     "SEO, content and being found by people looking for you."),
    ("Paid media", "paid-media", 40,
     "Advertising on Google, Meta, LinkedIn and everywhere else."),
    ("Social", "social", 50,
     "Publishing, community and creator partnerships."),
]

TAGS = [
    ("SEO", "seo"), ("Google Ads", "google-ads"), ("Analytics", "analytics"),
    ("Budgeting", "budgeting"), ("Reporting", "reporting"),
    ("Social media", "social-media"), ("Getting started", "getting-started"),
]


POSTS = [
    dict(
        title="How to choose the right marketing channels for your business",
        slug="choosing-marketing-channels",
        category="strategy",
        tags=["budgeting", "getting-started"],
        excerpt="Most channel decisions are made by imitation. Here is a "
                "more reliable way to narrow the list — starting with your "
                "margins rather than your competitors.",
        meta_description="A practical framework for choosing marketing "
                         "channels, based on deal value, buying intent and "
                         "sales cycle rather than on what competitors do.",
        content="""Ask most businesses why they advertise where they do, and
the honest answer is that a competitor does it, or someone once suggested
it, or they inherited the accounts. None of those is a reason.

Channel selection is one of the few marketing decisions with a genuinely
analytical answer. It depends on three things about your business, and
almost nothing about your industry.

## Start with what a customer is worth

Not revenue — margin, and over the lifetime of the relationship rather
than the first sale.

This number sets the ceiling on everything else. If a customer is worth
200 to you in gross margin, and you keep one in three qualified leads,
you can afford roughly 65 to acquire a lead before the channel stops
paying for itself. That single figure rules whole platforms in or out
before you have run anything.

It is also the number most businesses have never calculated. If you are
guessing at it, start there and come back to the channel question
afterwards. Everything downstream inherits the error.

## Then ask whether demand already exists

There is a real difference between a market where people are actively
searching for what you sell and one where they do not yet know they need
it.

**If demand exists**, search is usually the efficient entry point.
Someone typing "emergency plumber Colombo" has already decided; you are
competing to be the one they pick, not to create the want. Paid search
captures that immediately, SEO captures it durably and more cheaply once
established.

**If demand does not exist**, search has nothing to capture. A genuinely
new product gets found through paid social, content and partnerships —
channels that interrupt rather than respond. These cost more per customer
at the start, because you are paying to create the awareness as well as
convert it.

Running paid search for a product nobody searches for is one of the most
common and most expensive mistakes we see. The campaign is not broken.
There is simply nothing there.

## Then ask how long the decision takes

A 30 purchase and a 30,000 purchase need different machinery.

Short cycles suit channels that can close in one session: paid search,
paid social with a direct response offer, email to an existing list.

Long cycles need channels that can stay present across months of
consideration — content, email nurture, retargeting, LinkedIn for B2B.
Judging these on last-click conversions within a 30-day window will tell
you they do not work, which is a measurement failure rather than a
channel failure.

## What this rules out

Put the three together and the list usually shortens fast.

A B2B consultancy with a 40,000 deal value, an existing search market
and a six-month sales cycle should be on LinkedIn and paid search, with
content and email doing the holding work in between. Expensive clicks are
affordable and the long cycle is survivable.

A direct-to-consumer brand with a 45 product and a new category should be
on paid social with heavy creative testing, and nowhere near LinkedIn.
The click prices alone would make it impossible.

Neither answer required knowing the industry.

## Two things to do before you spend anything

**Set up conversion tracking first.** Choosing a channel without
measurement means you will be guessing at the result as well as the
choice. It is the cheapest work in this entire list and the most
frequently skipped.

**Start with one.** Three channels at a quarter of the necessary budget
each will all underperform, and you will not be able to say which could
have worked. Fund one properly, learn whether it pays, then add the next.

If you want a second opinion on where to start, [tell us about the
business](/contact/) and we will give you one — including when the answer
is that you do not need an agency yet.
""",
    ),

    dict(
        title="SEO or paid advertising: where should you invest first?",
        slug="seo-or-paid-advertising-first",
        category="search",
        tags=["seo", "google-ads", "budgeting"],
        excerpt="They answer different questions and run on different "
                "timescales. The right order depends mostly on how long you "
                "can wait — and on what you already have.",
        meta_description="SEO versus paid advertising: how the two differ in "
                         "speed, cost and durability, and a practical way to "
                         "decide which to fund first.",
        content="""This is usually framed as a rivalry. It is not one. They
do different jobs, and the real question is which job your business needs
done first.

## The honest comparison

**Paid advertising** buys attention immediately. Launch a campaign today
and you have traffic today. Stop paying and it stops the same afternoon.
You are renting access, and the rent is due every month.

**Search engine optimisation** earns attention slowly. Serious movement
usually takes months, and in a competitive market longer. Once earned it
costs comparatively little to hold, and it keeps producing while you
sleep. You are buying an asset, on a long payback.

Three consequences follow from that, and they are where most of the
confusion lives:

- Paid is faster to start and never gets cheaper. SEO is slow to start
  and gets cheaper per visit over time.
- Paid stops the day you stop paying. SEO decays over months, which is
  slower but also sneakier — by the time you notice, you have lost ground
  that takes longer to win back than it did to lose.
- Paid gives you data in days. That is its most underrated benefit, and
  the reason it is often the right *first* move even for a business whose
  long-term answer is SEO.

## Start with paid if

You need enquiries this quarter rather than next year. Cash flow does not
care about your content calendar.

You do not yet know which messages, offers or audiences work. Paid is the
fastest research instrument available: you can test five value
propositions in a fortnight for the price of one blog post, and the
answers feed directly into the SEO work afterwards.

You are launching something and have no search presence at all.

Your product is genuinely seasonal or time-bound. SEO cannot be switched
on for December.

## Start with SEO if

Your margins cannot sustain paid click prices. Some markets have been bid
up past the point where a modest deal value can absorb them. If the
arithmetic does not work, no amount of optimisation rescues it.

You already rank somewhere and are leaving obvious opportunity on the
table — ranking on page two for commercial terms is unconverted value
sitting there.

Your site has technical problems. This one is non-negotiable: paid
traffic landing on a slow, badly structured site converts poorly, so you
pay full price for a fraction of the result. Fix the foundation first,
whichever channel you then fund.

You are building for the long term and can fund the gap in the meantime.

## The answer most businesses arrive at

Run both, in sequence, and let the first fund the second.

Begin with paid to generate enquiries and, more importantly, to learn
what your market responds to. Use what you learn to direct the SEO work,
so your content targets terms you have *watched* convert rather than
terms a tool estimated. As organic traffic grows, shift budget from
renting attention to owning it — and keep paid running on the commercial
terms where it still pays.

That sequence works because the two channels inform each other. Search
query reports from a paid campaign are the best keyword research
available: real queries from real buyers, with conversion data attached.
Using it to steer content is free, and almost nobody does it.

## What to measure, and what to ignore

For paid, measure cost per customer and the margin that survives it.
Click-through rate and cost per click are diagnostics for finding
problems, not results to report upward.

For SEO, measure rankings and traffic for terms with commercial intent,
and conversions from organic. Total traffic is a flattering number and a
poor one: a thousand visitors reading a glossary page are worth less than
ten reading a pricing page.

Judge both over the right window. Assessing SEO at six weeks or a paid
campaign at four days will tell you something, but not what you asked.

If you are not sure which applies to you, that is usually a measurement
question rather than a strategy one — and [it can be answered in a
fortnight](/services/category/analytics/).
""",
    ),

    dict(
        title="Understanding cost per lead and ROAS",
        slug="understanding-cost-per-lead-and-roas",
        category="measurement",
        tags=["analytics", "reporting", "google-ads"],
        excerpt="Two of the most quoted numbers in marketing, and two of the "
                "most misread. What each actually tells you, and the ways "
                "both can be quietly wrong.",
        meta_description="What cost per lead and return on ad spend really "
                         "measure, how each can mislead, and the numbers to "
                         "read alongside them.",
        content="""If you have ever sat in a marketing review where everyone
agreed the numbers looked good and nobody could say whether the business
had made money, you have met these two metrics.

Both are useful. Both are routinely reported in ways that hide more than
they show.

## Cost per lead

**Cost per lead** is total spend divided by the number of leads it
produced. Spend 2,000, get 40 enquiries, and your cost per lead is 50.

The trouble starts at the word *lead*.

If "lead" means anyone who filled in a form, that figure includes the
students, the job applicants, the suppliers pitching to you and the
person who misread what you sell. We have seen a campaign halve its cost
per lead and reduce actual sales, because the cheaper leads were cheaper
for a reason.

**Cost per qualified lead** is the number worth reporting. Define
"qualified" as something your sales team would recognise — right budget,
right sector, actually wants the thing — and measure against that. It
will be a worse-looking number and a far more useful one.

Then carry it one step further. What you really need is **cost per
customer**: cost per qualified lead divided by your close rate. If
qualified leads cost 120 and you win one in four, each customer costs
480 to acquire. Set that against lifetime margin and you finally have a
sentence worth saying out loud: *this channel makes money*, or it does
not.

## Return on ad spend

**ROAS** is revenue attributed to advertising divided by the cost of that
advertising. Spend 1,000, generate 4,000 in tracked revenue, and your
ROAS is 4, or 400%.

It is the standard e-commerce metric, and it has three well-known
failure modes that get mentioned far less often than the number itself.

**It uses revenue, not margin.** A ROAS of 4 sounds healthy. If your
gross margin is 20%, that 4,000 of revenue carries 800 of margin against
1,000 of spend, and you lost money being successful. Work in **POAS** —
profit on ad spend — or at minimum know the break-even ROAS your margin
implies, and report against that line rather than against a round number
somebody liked.

**It counts sales that would have happened anyway.** Brand campaigns are
the clearest case: someone who searched your company name was already
coming. Attributing that sale to the ad that caught them on the way in
makes the campaign look excellent and tells you nothing about whether it
created anything. The only reliable way to find out is to turn it off
for long enough to see.

**It depends entirely on the attribution window.** The same campaign can
report a ROAS of 2 or 6 depending on whether you count conversions within
one day or thirty, and whether view-throughs count. Neither number is a
lie. Changing the window without saying so, and then comparing months, is.

## The numbers to read alongside them

Neither metric means much alone.

- **Conversion rate** tells you whether a disappointing cost per lead is
  a traffic problem or a landing page problem. Cheap clicks that do not
  convert are not cheap.
- **Average order value** or deal size, because a rising cost per
  customer is fine if customers got bigger.
- **Lifetime value**, especially for subscriptions and repeat purchase.
  Judging a subscription business on first-order ROAS will make you turn
  off the campaigns that are working.
- **Lead-to-customer rate by source**, which is how you discover that the
  channel with the best cost per lead has the worst close rate.

## Three practical habits

**Define your terms once, and write them down.** Most arguments about
marketing performance are two people using the same word differently.

**Report the same window every month.** If you change it, say so in the
report, and restate the previous period on the new basis.

**Put a break-even line on the chart.** A ROAS of 3.2 means nothing until
you know that 2.8 is where you stop making money. With the line drawn,
the number interprets itself — and everyone in the room can read it
without a marketing background.

That last habit is most of what separates reporting people act on from
reporting people nod at.
""",
    ),

    dict(
        title="Common tracking mistakes that make marketing data unreliable",
        slug="common-tracking-mistakes",
        category="measurement",
        tags=["analytics", "reporting"],
        excerpt="When your platforms disagree, one of them is usually "
                "counting something you did not intend. Here are the errors "
                "we find most often, and how to check for each.",
        meta_description="The tracking errors that most often corrupt "
                         "marketing data — double counting, internal "
                         "traffic, attribution mismatches — and how to find "
                         "them.",
        content="""Almost every "which channel is working?" argument we are
asked to settle turns out to be a tracking problem. The platforms
disagree, nobody knows which to believe, and the decision gets made on
whichever number supports the answer somebody already preferred.

These are the causes we find most often, roughly in order of frequency.

## Counting the same conversion more than once

A conversion fires on the form submission *and* on the thank-you page.
Or it fires on page load, and the page gets refreshed. Or Tag Manager and
a hard-coded platform tag both report it.

**The symptom:** your conversion count comfortably exceeds the number of
enquiries your sales team actually received.

**The check:** pick one real customer and trace their journey through
every platform. If one person shows up as two conversions, you have found
it. Do this with five customers once a quarter; it takes an hour and it
catches most of what is on this page.

## Your own team in the data

Staff visits, developers testing the site, and the agency checking its
own work all get counted. On a small site this is not a rounding error —
it can be a quarter of your sessions, and it is concentrated on exactly
the pages you care about most.

**The symptom:** suspicious traffic to admin pages, a bounce rate that is
oddly good, conversions at 9am on a Monday from your own city.

**The check:** filter internal addresses in analytics, and exclude your
office network. Keep an unfiltered view as well, so you can tell the
difference between a filter working and a filter that broke.

## Form submissions counted before they succeed

The conversion fires when the button is clicked, not when the submission
validates. Every failed submission, every mistyped email, every bot that
trips the honeypot is counted as a lead.

**The symptom:** a steadily growing gap between conversions reported and
enquiries received.

**The check:** compare the platform's count against rows in your own
database for the same period. Your database is the one telling the truth;
anything above it is phantom.

## Attribution windows nobody agreed on

Google Ads defaults differ from Meta's, which differ from your
analytics. Each counts a conversion the others do not, and the same sale
appears in three reports.

**The symptom:** the sum of conversions across platforms exceeds your
actual sales — often substantially.

**The check:** total what every platform claims and compare it to orders
in your own system. If platforms claim 150 sales and you made 95, you are
not measuring; you are collecting opinions. Pick one source as the
arbiter — usually your own database — and treat platform figures as
estimates for optimisation only.

## Tracking lost in a redesign

The site gets rebuilt, the tags do not come across, and nobody notices
for six weeks because the reports still render — just with smaller
numbers that get blamed on seasonality.

**The symptom:** a step change in the data that lines up suspiciously
well with a deployment date.

**The check:** add tracking verification to your release checklist. After
any significant site change, submit a test enquiry and confirm it appears
in every platform within the hour.

## Cross-domain journeys breaking the session

Your site is on one domain and your booking system or checkout is on
another. Without cross-domain configuration, analytics treats the handoff
as a brand-new visitor from a referral — so the conversion is credited to
your own checkout provider rather than to the campaign that earned it.

**The symptom:** your payment processor appears as a top traffic source.
It is worth looking for this one specifically, because it looks like a
real finding rather than a fault.

**The check:** look at your referral sources for a domain you own or pay.

## Consent handled as an afterthought

Where a consent banner is in use, tracking that fires before consent is a
compliance problem, and tracking that never fires after consent is given
is a data problem. Both are common, frequently in the same
implementation.

**The check:** test the site twice — once accepting, once declining — and
confirm that what fires in each case is what you intended.

## A reasonable standard to hold yourself to

You do not need perfect data. You need data that is **consistently**
wrong in a known direction, and that you can reconcile against something
real.

Three habits get you most of the way:

1. Reconcile against your own database monthly. Platform numbers are
   estimates; your records are facts.
2. Document what each conversion event actually measures, so next year's
   argument is shorter than this year's.
3. Re-verify after every site change, not every quarter.

If your numbers currently disagree and nobody can say why, that is a
[measurement audit](/services/category/analytics/) rather than a
marketing problem — and it is usually a short piece of work with an
unusually good return.
""",
    ),
]


def seed(apps, schema_editor):
    Category = apps.get_model("cms", "Category")
    Tag = apps.get_model("cms", "Tag")
    BlogPost = apps.get_model("cms", "BlogPost")

    # Only into an empty blog. An agency that has started publishing
    # should not find four of ours appearing underneath their own.
    if BlogPost.objects.exists():
        return

    now = timezone.now()

    categories = {}
    for name, slug, order, description in CATEGORIES:
        categories[slug], _ = Category.objects.get_or_create(
            slug=slug,
            defaults=dict(name=name, order=order, description=description,
                          is_visible=True, created_at=now, updated_at=now),
        )

    tags = {}
    for name, slug in TAGS:
        tags[slug], _ = Tag.objects.get_or_create(
            slug=slug,
            defaults=dict(name=name, is_visible=True,
                          created_at=now, updated_at=now),
        )

    for index, spec in enumerate(POSTS):
        post = BlogPost.objects.create(
            title=spec["title"], slug=spec["slug"],
            excerpt=spec["excerpt"], content=spec["content"].strip(),
            category=categories[spec["category"]],
            status="published",
            # Spaced apart so the listing has a sensible order rather
            # than four posts sharing one timestamp.
            published_at=now - timedelta(days=index * 7),
            meta_description=spec["meta_description"],
            created_at=now, updated_at=now,
        )
        post.tags.set([tags[slug] for slug in spec["tags"]])


def unseed(apps, schema_editor):
    BlogPost = apps.get_model("cms", "BlogPost")
    BlogPost.objects.filter(slug__in=[spec["slug"] for spec in POSTS]).delete()


class Migration(migrations.Migration):

    dependencies = [("cms", "0007_seed_professional_content")]

    operations = [migrations.RunPython(seed, unseed)]
