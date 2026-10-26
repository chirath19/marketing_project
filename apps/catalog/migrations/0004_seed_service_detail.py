"""Give every service enough detail to be bought from.

A catalogue card tells somebody a service exists. It does not tell them
whether it is meant for their business, what they will actually receive,
or what the first month looks like — and those are the questions that
decide whether an enquiry gets sent.

So each service here gains a full description, who it suits, what is
delivered, how it runs and how it is reported, plus the two or three
questions that service genuinely attracts. All of it is editable in the
staff dashboard.

Written per service on purpose. The same six generic steps pasted under
every heading reads as a template and tells a buyer nothing.

No performance claims appear anywhere below. We can describe what we do
without inventing what it returned for someone else.
"""

from decimal import Decimal

from django.db import migrations
from django.utils import timezone


#: Services the catalogue did not yet carry. Same shape as the original
#: seed: name, slug, category, short description, price, billing,
#: featured, feature labels.
NEW_SERVICES = [
    ("On-page SEO", "on-page-seo", "search",
     "Titles, structure, internal links and content fixes across the pages "
     "that matter most.", Decimal("1100"), "one_time", False,
     ["Page-level keyword mapping", "Titles and meta descriptions",
      "Heading structure and internal links", "Content gap fixes"]),

    ("Keyword and market research", "keyword-research", "search",
     "What your market actually searches for, what it is worth, and who "
     "currently owns it.", Decimal("950"), "one_time", False,
     ["Search demand analysis", "Intent and funnel mapping",
      "Competitor visibility review", "Priority target list"]),

    ("SEO content strategy", "seo-content-strategy", "search",
     "A content plan built from search demand rather than from whatever is "
     "easiest to write.", Decimal("1400"), "one_time", False,
     ["Topic and cluster planning", "Briefs for each piece",
      "Publishing calendar", "Measurement plan"]),

    ("Paid media strategy", "paid-media-strategy", "paid",
     "Which platforms deserve your budget, how it should be split, and what "
     "each part has to return.", Decimal("1600"), "one_time", False,
     ["Channel and platform selection", "Budget allocation model",
      "Audience and messaging plan", "Target and measurement framework"]),

    ("Campaign audit", "campaign-audit", "paid",
     "An independent review of ad accounts you already run, with a ranked "
     "list of what to change.", Decimal("1200"), "one_time", False,
     ["Account structure review", "Wasted spend analysis",
      "Tracking and conversion check", "Prioritised fix list"]),

    ("Retargeting campaigns", "retargeting-campaigns", "paid",
     "Reaching people who already visited, without following them around "
     "until they resent it.", Decimal("1300"), "monthly", False,
     ["Audience segmentation", "Creative and sequencing",
      "Frequency and exclusion rules", "Performance reporting"]),

    ("Content planning", "content-planning", "social",
     "A publishing calendar your team can actually keep to, built around "
     "real capacity.", Decimal("900"), "monthly", False,
     ["Monthly content calendar", "Format and channel mix",
      "Copy direction and hooks", "Review and approval cycle"]),

    ("Short-form video campaign", "short-form-video", "social",
     "A batch of vertical videos planned, produced and published across "
     "your channels.", Decimal("2400"), "monthly", False,
     ["Concept and scripting", "Production scheduling",
      "Editing and captioning", "Publishing and performance review"]),

    ("Community management", "community-management", "social",
     "Replies, comments and messages handled on a predictable schedule.",
     Decimal("1100"), "monthly", False,
     ["Daily comment and message handling", "Response tone guidelines",
      "Escalation to your team", "Sentiment and volume reporting"]),

    ("Email marketing strategy", "email-marketing-strategy", "email",
     "What to send, to whom and how often — before anybody designs a "
     "template.", Decimal("1300"), "one_time", False,
     ["List and segmentation review", "Lifecycle and flow mapping",
      "Content and cadence plan", "Deliverability assessment"]),

    ("Email campaign analysis", "email-campaign-analysis", "email",
     "A review of what your emails are actually doing, beyond the open "
     "rate.", Decimal("750"), "one_time", False,
     ["Engagement and revenue analysis", "Segment performance comparison",
      "Subject and content testing review", "Recommendations"]),

    ("Conversion tracking setup", "conversion-tracking", "analytics",
     "Every action that matters, measured correctly and verified end to "
     "end.", Decimal("1000"), "one_time", False,
     ["Conversion definition workshop", "Event and goal configuration",
      "Cross-platform deduplication", "Verification and documentation"]),

    ("Measurement audit", "measurement-audit", "analytics",
     "Finding out why your numbers disagree with each other — and which one "
     "to trust.", Decimal("1100"), "one_time", False,
     ["Tag and data layer review", "Platform discrepancy analysis",
      "Attribution review", "Remediation plan"]),

    ("Digital marketing strategy", "digital-marketing-strategy", "strategy",
     "The whole picture: channels, budget, targets and sequence, in one "
     "plan.", Decimal("3200"), "one_time", True,
     ["Business and market discovery", "Channel strategy and budget split",
      "Target setting and measurement plan", "Twelve-month roadmap"]),

    ("Campaign planning", "campaign-planning", "strategy",
     "Planning a launch, a season or a product push across every channel at "
     "once.", Decimal("1800"), "one_time", False,
     ["Objective and audience definition", "Channel and message plan",
      "Timeline and asset schedule", "Measurement framework"]),

    ("Marketing performance review", "performance-review", "strategy",
     "A quarterly look at what the whole programme returned, and what "
     "should change.", Decimal("1200"), "one_time", False,
     ["Cross-channel performance analysis", "Target and budget review",
      "Competitive position check", "Recommendations for next quarter"]),
]


#: slug -> (full_description, ideal_for, deliverables, process, reporting)
DETAIL = {
    "technical-seo-audit": (
        "Search engines have to be able to reach your pages, read them and "
        "decide they are worth ranking. When any of that breaks, no amount "
        "of content or link building compensates — you are paying to fill a "
        "bucket with a hole in it.\n\n"
        "This audit finds the hole. We crawl the site the way a search "
        "engine does, compare that against what is actually indexed, and "
        "measure how the pages perform for real visitors. What comes back "
        "is not a 200-page export: it is a ranked list of what is costing "
        "you, what it will take to fix, and what you can safely ignore.",
        "Sites that have been rebuilt, migrated or replatformed\n"
        "Businesses whose rankings dropped without an obvious cause\n"
        "Large or e-commerce sites where crawl budget is a real constraint\n"
        "Anyone about to invest in content or links and wanting the "
        "foundations checked first",
        "Full crawl report with issues ranked by impact\n"
        "Index coverage and canonical analysis\n"
        "Core Web Vitals assessment on real-visitor data\n"
        "Prioritised fix list with effort estimates\n"
        "Walkthrough call with your developer",
        "Crawl the site and pull index, performance and search console data\n"
        "Reproduce and verify each issue by hand before it goes on the list\n"
        "Rank findings by traffic at risk against effort to fix\n"
        "Deliver the report and walk your developers through it\n"
        "Re-check the fixes once they ship",
        "A single written report, plus a verification pass after your team "
        "has made the changes.",
    ),
    "seo-growth-retainer": (
        "Search results are won slowly and lost quickly. A retainer is the "
        "honest shape for that work: continuous content, technical "
        "maintenance and authority building, reviewed every month against "
        "the positions that actually bring you customers.\n\n"
        "We do not report on a vanity keyword list. We report on the terms "
        "with commercial intent in your market, where you rank for them, "
        "and what moved.",
        "Businesses committed to search as a long-term channel\n"
        "Sites with existing traffic that has plateaued\n"
        "Competitive markets where one-off work gets overtaken\n"
        "Teams without in-house SEO capacity",
        "Monthly content plan and published pieces\n"
        "Ongoing technical fixes and monitoring\n"
        "Link acquisition activity and placements\n"
        "Monthly ranking, traffic and conversion report",
        "Baseline the site, the market and the current positions\n"
        "Agree the target terms that have commercial value\n"
        "Run a monthly cycle of content, technical work and outreach\n"
        "Review performance against targets each month\n"
        "Reset priorities quarterly as positions change",
        "A monthly report in your workspace covering rankings, traffic, "
        "conversions and the work completed.",
    ),
    "local-search": (
        "For a business that serves a place, most of the opportunity is in "
        "the map pack and not in the classic results. That is a different "
        "discipline: proximity, profile completeness, categories, reviews "
        "and consistent business details across the web.\n\n"
        "We manage all of it, for one location or for many.",
        "Shops, restaurants and venues with physical premises\n"
        "Trades and service businesses covering defined areas\n"
        "Clinics, practices and firms competing locally\n"
        "Multi-location businesses with inconsistent listings",
        "Fully optimised Google Business Profile\n"
        "Location landing pages where they are justified\n"
        "Citation audit and clean-up across directories\n"
        "Review generation process your team can run\n"
        "Monthly local visibility report",
        "Audit the profile, the listings and the local competition\n"
        "Correct and complete the profile and every inconsistent citation\n"
        "Build or improve the location pages on your site\n"
        "Set up a review request process that fits how you serve customers\n"
        "Monitor local rankings and respond to profile changes",
        "A monthly report covering map visibility, profile actions, calls "
        "and direction requests.",
    ),
    "on-page-seo": (
        "On-page work is the cheapest SEO there is: the pages already "
        "exist, they already have some authority, and most of them are "
        "under-performing for reasons that take an afternoon to fix.\n\n"
        "We map each important page to the thing it should rank for, then "
        "fix the titles, structure, internal linking and content gaps that "
        "are holding it short.",
        "Sites with plenty of pages and thin rankings\n"
        "Businesses who have invested in content without a keyword map\n"
        "Anyone wanting measurable gains without a long retainer\n"
        "Sites preparing for a content or link campaign",
        "Keyword-to-page map for the pages that matter\n"
        "Rewritten titles and meta descriptions\n"
        "Heading and internal link recommendations\n"
        "Content gap list per page\n"
        "Implementation guidance or hands-on changes",
        "Identify which pages carry commercial value\n"
        "Map each to a primary and secondary search intent\n"
        "Audit the current on-page signals against that intent\n"
        "Produce the changes, page by page\n"
        "Hand over for implementation, or implement directly",
        "A single deliverable with page-level recommendations, plus a "
        "follow-up position check.",
    ),
    "keyword-research": (
        "Most keyword research produces a spreadsheet nobody opens. The "
        "useful version answers three questions: what does this market "
        "search for, which of those searches are worth money, and who "
        "currently has them.\n\n"
        "That is what you get — a prioritised target list you can plan "
        "content, ads and site structure around.",
        "Businesses entering a new market or launching a product\n"
        "Anyone planning content and wanting to plan it from demand\n"
        "Teams whose current targets were chosen by instinct\n"
        "Sites being restructured",
        "Full search demand analysis for your market\n"
        "Intent classification across the funnel\n"
        "Competitor visibility comparison\n"
        "Prioritised target list with volume and difficulty",
        "Seed the research from your products, customers and competitors\n"
        "Expand and cluster the full demand picture\n"
        "Classify by intent and commercial value\n"
        "Assess who currently ranks and how entrenched they are\n"
        "Deliver the prioritised list with recommended next steps",
        "A single research deliverable, reviewed with you on a call.",
    ),
    "seo-content-strategy": (
        "Publishing more is not a strategy. Publishing the right things, in "
        "an order that builds authority on a topic rather than scattering "
        "it, is.\n\n"
        "We plan content around clusters: the pages that establish you on a "
        "subject, and the supporting pieces that make the central one "
        "credible. Each piece gets a brief specific enough to be written by "
        "anyone competent.",
        "Businesses with a content budget and no plan for it\n"
        "Teams publishing regularly without seeing search returns\n"
        "Companies entering a competitive informational market\n"
        "In-house writers who need direction rather than supervision",
        "Topic cluster map for your market\n"
        "Individual briefs for each planned piece\n"
        "Publishing calendar with priorities\n"
        "Internal linking plan\n"
        "Measurement framework for content performance",
        "Establish the topics your business can credibly own\n"
        "Map demand and competition within each\n"
        "Design the cluster structure and internal linking\n"
        "Write briefs for each piece, in priority order\n"
        "Set the measurement so performance is attributable",
        "A strategy document and calendar, with a review once the first "
        "pieces have been live long enough to judge.",
    ),
    "google-ads-management": (
        "Google Ads will spend whatever you give it. Whether that spend "
        "produces customers depends on account structure, query control, "
        "landing page relevance and conversion tracking that reports the "
        "truth.\n\n"
        "We manage against cost per customer. Clicks, impressions and "
        "click-through rate are diagnostics we use — they are not what we "
        "report success on.",
        "Businesses with a defined product or service and a budget to test\n"
        "E-commerce needing Shopping and Performance Max run properly\n"
        "Companies currently running ads without conversion tracking\n"
        "Anyone whose cost per lead has drifted upward unexplained",
        "Restructured or newly built campaigns\n"
        "Conversion tracking verified end to end\n"
        "Weekly optimisation and search term management\n"
        "Ad copy and landing page testing programme\n"
        "Monthly performance report against agreed targets",
        "Audit the existing account, or build from the keyword research\n"
        "Fix or implement conversion tracking before spend increases\n"
        "Build the campaign structure and launch controlled\n"
        "Optimise weekly on search terms, bids and creative\n"
        "Review monthly against cost per customer and adjust the plan",
        "A monthly report on spend, conversions and cost per customer, "
        "plus weekly change notes in your workspace.",
    ),
    "meta-ads-management": (
        "On Meta the creative is the targeting. Audience settings matter "
        "far less than they used to; what decides performance is whether "
        "the work stops somebody scrolling and says something true about "
        "your product.\n\n"
        "So this is a creative testing programme with media buying attached, "
        "rather than the other way round.",
        "Consumer brands and e-commerce businesses\n"
        "Services with a visual or demonstrable product\n"
        "Businesses whose Meta results have declined since tracking changes\n"
        "Anyone with creative capacity wanting it tested properly",
        "Campaign structure built for creative testing\n"
        "Monthly creative refresh and iteration\n"
        "Conversions API and pixel configuration\n"
        "Audience and exclusion management\n"
        "Monthly performance report",
        "Audit tracking first — on Meta, broken measurement is invisible\n"
        "Establish the creative angles worth testing\n"
        "Launch structured tests rather than one campaign\n"
        "Scale what wins, retire what does not, refresh monthly\n"
        "Report on cost per purchase or lead, not engagement",
        "A monthly report on spend, results and cost per outcome, with "
        "creative performance broken out.",
    ),
    "linkedin-lead-generation": (
        "LinkedIn costs several times what other platforms do per click, "
        "and for the right business it is still the cheapest route to a "
        "qualified conversation — because nowhere else lets you reach a job "
        "title at a company size in an industry.\n\n"
        "It only works where the deal value supports the click price. We "
        "will tell you before you start if we think it does not.",
        "B2B businesses with a considered, higher-value sale\n"
        "Companies selling to a definable job title\n"
        "Professional services and consultancies\n"
        "SaaS and technology businesses with a sales team",
        "Audience definitions by role, company and industry\n"
        "Lead generation form campaigns\n"
        "Creative and message testing\n"
        "Lead handover into your CRM or inbox\n"
        "Monthly cost-per-lead reporting",
        "Define the target account and role profile precisely\n"
        "Build the audiences and the lead capture\n"
        "Test messages against each segment\n"
        "Qualify the leads coming through and feed that back into targeting\n"
        "Report on cost per qualified lead, not raw volume",
        "A monthly report on spend, leads and cost per qualified lead.",
    ),
    "paid-media-strategy": (
        "Before you decide how to run campaigns, you have to decide where "
        "to run them and what each one has to return. Most budget is wasted "
        "at that level, not at the level of bid adjustments.\n\n"
        "This is the planning work: which platforms suit your economics, "
        "how to split the budget between proving and scaling, and what "
        "number each channel has to hit to deserve its share.",
        "Businesses about to invest meaningfully in paid media\n"
        "Companies running several platforms with no coordinating plan\n"
        "Teams whose budget is set by habit rather than return\n"
        "Anyone planning a launch across multiple channels",
        "Channel selection with the reasoning behind it\n"
        "Budget allocation model\n"
        "Audience and messaging plan per platform\n"
        "Target and measurement framework\n"
        "Phased rollout plan",
        "Understand the unit economics the marketing has to work within\n"
        "Assess which platforms can realistically deliver at that cost\n"
        "Model the budget split between testing and scaling\n"
        "Set the target each channel must hit\n"
        "Produce the rollout plan and measurement framework",
        "A strategy document, presented and talked through.",
    ),
    "campaign-audit": (
        "An audit by somebody who is not running the account and does not "
        "need it to look good. We go through structure, targeting, spend "
        "distribution, creative and — most often the real problem — whether "
        "the conversion data is telling the truth.\n\n"
        "You get the findings whether or not you work with us afterwards.",
        "Businesses unsure whether their current agency is performing\n"
        "Accounts where cost per result has crept up\n"
        "Companies taking ad management in-house\n"
        "Anyone before renewing a management contract",
        "Account structure and settings review\n"
        "Wasted spend analysis with figures\n"
        "Conversion tracking verification\n"
        "Creative and landing page assessment\n"
        "Ranked list of changes with expected impact",
        "Get read access to the accounts and the analytics\n"
        "Verify what the conversion data actually measures\n"
        "Analyse spend against results at every level\n"
        "Identify waste, gaps and structural problems\n"
        "Deliver findings ranked by what they are worth",
        "A written audit and a walkthrough call.",
    ),
    "retargeting-campaigns": (
        "Most people do not buy on a first visit. Retargeting is how you "
        "stay in the consideration set — and it is also the easiest way to "
        "irritate the people closest to buying, if frequency and exclusions "
        "are left to chance.\n\n"
        "We segment by what someone actually did, sequence the message "
        "accordingly, and cap exposure.",
        "E-commerce businesses with meaningful traffic\n"
        "Longer consideration purchases\n"
        "Businesses with abandoned carts or incomplete enquiries\n"
        "Anyone whose retargeting currently shows one ad to everybody",
        "Audience segmentation by behaviour and recency\n"
        "Sequenced creative per segment\n"
        "Frequency caps and exclusion rules\n"
        "Cross-platform configuration\n"
        "Monthly performance reporting",
        "Map the journey and the points where people drop out\n"
        "Build audiences for each meaningful drop-out point\n"
        "Write and produce creative appropriate to each stage\n"
        "Set frequency caps and purchase exclusions before launch\n"
        "Review and refresh creative monthly",
        "A monthly report on reach, frequency, conversions and cost per "
        "recovered sale.",
    ),
    "social-media-management": (
        "Consistency beats brilliance on social. An account that posts "
        "something decent every week outperforms one that posts something "
        "excellent whenever somebody has time.\n\n"
        "We take over the rhythm: planning, producing, publishing and "
        "replying across two channels, with the creative direction reviewed "
        "monthly against what is actually landing.",
        "Businesses whose social accounts have gone quiet\n"
        "Teams without the capacity to post consistently\n"
        "Brands wanting a coherent voice across channels\n"
        "Companies where social is handled by whoever is free",
        "Monthly content calendar, agreed in advance\n"
        "Designed and written posts across two channels\n"
        "Scheduled publishing\n"
        "Community replies within agreed hours\n"
        "Monthly performance and audience report",
        "Agree the voice, the channels and the posting rhythm\n"
        "Plan each month's calendar and get it approved\n"
        "Produce and schedule the content\n"
        "Handle replies and messages on the agreed schedule\n"
        "Review what performed and adjust the next month",
        "A monthly report on reach, engagement, audience growth and the "
        "posts that worked.",
    ),
    "content-planning": (
        "The reason content calendars fail is that they are built around "
        "ambition rather than capacity. A plan for three posts a week, from "
        "a team that can manage one, produces nothing and a sense of "
        "failure.\n\n"
        "We plan around what your team can genuinely sustain, and make each "
        "piece count for more.",
        "In-house teams who want direction, not delivery\n"
        "Businesses with a subject-matter expert and no plan\n"
        "Companies whose posting is reactive and inconsistent\n"
        "Teams who have tried a calendar and abandoned it",
        "Monthly content calendar\n"
        "Format and channel mix recommendations\n"
        "Copy direction, hooks and angles per piece\n"
        "Review and approval cycle that fits your team",
        "Establish honestly what your team can produce each month\n"
        "Agree the themes and formats worth the effort\n"
        "Build the calendar around real capacity\n"
        "Supply direction for each piece\n"
        "Review monthly and adjust the plan to reality",
        "A monthly calendar in your workspace, with a short review of how "
        "the previous month performed.",
    ),
    "short-form-video": (
        "Short vertical video is where organic reach still exists, and the "
        "barrier is production throughput rather than ideas. One polished "
        "film a quarter loses to twelve adequate ones.\n\n"
        "We plan, produce and publish in batches, so volume is achievable "
        "without the quality collapsing.",
        "Brands with something visual to show\n"
        "Businesses wanting organic reach rather than paid\n"
        "Companies with a presenter or expert willing to be on camera\n"
        "Teams who have tried video and found it unsustainable",
        "Concepts and scripts for each batch\n"
        "Production schedule and shot lists\n"
        "Edited, captioned videos ready to publish\n"
        "Publishing across your channels\n"
        "Monthly performance review",
        "Agree the formats and angles worth producing repeatedly\n"
        "Script and plan a batch at once\n"
        "Produce in a single scheduled session\n"
        "Edit, caption and publish on a rhythm\n"
        "Review what held attention and plan the next batch from it",
        "A monthly report on views, retention and follower growth per "
        "format.",
    ),
    "community-management": (
        "An unanswered comment is a worse signal than no comment. Community "
        "management is unglamorous and it is the part of social most often "
        "dropped when the team gets busy.\n\n"
        "We take it on a defined schedule, within a tone you approve, and "
        "escalate anything that should reach a person at your end.",
        "Accounts receiving more messages than the team can answer\n"
        "Businesses where response times have become a complaint\n"
        "Brands wanting a consistent voice in replies\n"
        "Companies running campaigns that will generate inbound",
        "Daily handling of comments, replies and messages\n"
        "Agreed tone and response guidelines\n"
        "Escalation path to your team for anything sensitive\n"
        "Monthly volume and sentiment report",
        "Agree the tone, the boundaries and what must be escalated\n"
        "Document standard responses for recurring questions\n"
        "Handle the daily queue on the agreed schedule\n"
        "Escalate complaints and opportunities to your team\n"
        "Report monthly on volume, themes and sentiment",
        "A monthly report on volume, response times, themes and sentiment.",
    ),
    "creator-partnerships": (
        "Creator marketing goes wrong in the selection, not the execution. "
        "Follower counts are the least useful signal available; audience "
        "overlap, engagement quality and whether the creator would "
        "plausibly use your product matter far more.\n\n"
        "We handle sourcing, vetting, briefing, contracting and measurement "
        "so you are not negotiating rates by direct message.",
        "Consumer brands with a product people can show\n"
        "Businesses wanting reach in a specific community\n"
        "Companies who have run creator campaigns that underdelivered\n"
        "Brands needing content as well as reach",
        "Vetted creator shortlist with the reasoning\n"
        "Briefs and contract templates\n"
        "Content review and approval management\n"
        "Usage rights secured for your own channels\n"
        "Campaign performance report",
        "Define the audience you are trying to reach, not the follower count\n"
        "Source and vet creators against audience overlap and engagement\n"
        "Brief, negotiate and contract, including usage rights\n"
        "Manage production and approvals\n"
        "Measure against agreed outcomes and brief the next round",
        "A campaign report covering reach, engagement, referral traffic and "
        "any tracked conversions.",
    ),
    "email-automation-setup": (
        "Automated flows are the highest-return email you will ever send, "
        "because they reach somebody at the moment they are already "
        "thinking about you. They are also the thing most businesses mean "
        "to set up and never do.\n\n"
        "We map, write, build and test the flows, then hand them over "
        "documented so your team can maintain them.",
        "E-commerce businesses without abandoned cart recovery\n"
        "Any business with a sign-up that gets no welcome sequence\n"
        "Companies with a dormant customer list\n"
        "Teams who have a platform and have never used the automation in it",
        "Flow maps for each automation\n"
        "Written and designed emails\n"
        "Built and tested flows in your platform\n"
        "Documentation for your team\n"
        "Handover session",
        "Map the moments worth automating against your customer journey\n"
        "Design the sequence, timing and exit conditions for each flow\n"
        "Write and design every email in the sequence\n"
        "Build in your platform and test every path\n"
        "Hand over with documentation and a walkthrough",
        "A build report, plus a performance review once the flows have run "
        "long enough to judge.",
    ),
    "monthly-newsletter": (
        "A newsletter is a standing invitation to an audience that already "
        "chose you. It is the cheapest channel you have, and the one most "
        "likely to be skipped because nobody owns it.\n\n"
        "We own it: strategy, writing, design and sending, every month, "
        "whether or not your team had a busy week.",
        "Businesses with a list they are not using\n"
        "Companies whose newsletter has become irregular\n"
        "Professional services wanting to stay present between purchases\n"
        "Retailers with repeat-purchase customers",
        "Monthly content plan\n"
        "Written and designed email\n"
        "Segmentation and scheduling\n"
        "Send management\n"
        "Performance report",
        "Agree the themes and the value the newsletter offers its readers\n"
        "Plan and write each issue\n"
        "Design and build in your platform\n"
        "Segment, schedule and send\n"
        "Report on engagement and revenue, and adjust",
        "A monthly report on opens, clicks, unsubscribes and attributable "
        "revenue.",
    ),
    "email-marketing-strategy": (
        "Most email problems are strategy problems wearing a design "
        "costume. Sending more does not fix a list that is poorly "
        "segmented, a cadence nobody asked for, or a reputation that is "
        "putting you in the spam folder.\n\n"
        "This is the planning work that comes before anyone opens a "
        "template editor.",
        "Businesses whose email engagement is declining\n"
        "Companies with a list and no segmentation\n"
        "Teams about to invest in a new email platform\n"
        "Anyone with deliverability problems",
        "List health and segmentation review\n"
        "Lifecycle and flow map\n"
        "Content themes and cadence plan\n"
        "Deliverability assessment with remediation steps",
        "Audit the list, the segmentation and the sending history\n"
        "Check authentication and deliverability signals\n"
        "Map the lifecycle and where email should intervene\n"
        "Plan the cadence and the content that justifies it\n"
        "Deliver the strategy with a prioritised sequence of work",
        "A strategy document, reviewed on a call.",
    ),
    "email-campaign-analysis": (
        "Open rates stopped being reliable when mail clients began "
        "pre-fetching images, and they were never a business outcome "
        "anyway. The question is which segments respond, which content "
        "earns clicks, and what any of it is worth.\n\n"
        "We analyse what your campaigns have actually done and tell you "
        "what to change.",
        "Businesses sending regularly without analysing results\n"
        "Companies whose engagement has dropped\n"
        "Teams wanting to justify email as a channel internally\n"
        "Anyone planning a significant change to their programme",
        "Engagement and revenue analysis by campaign\n"
        "Segment performance comparison\n"
        "Subject line and content testing review\n"
        "Prioritised recommendations",
        "Pull campaign and revenue data from your platform\n"
        "Analyse performance by segment, content type and timing\n"
        "Separate real engagement from inflated open metrics\n"
        "Identify what correlates with revenue\n"
        "Deliver recommendations in priority order",
        "A written analysis with recommendations.",
    ),
    "tracking-setup": (
        "Almost every marketing argument we are asked to settle turns out "
        "to be a measurement problem. Two platforms report different "
        "conversion counts, nobody knows which is right, and decisions get "
        "made on whichever number supports the preferred answer.\n\n"
        "We install tracking properly, test it end to end, and document "
        "what each number means.",
        "Businesses about to start or scale paid advertising\n"
        "Sites that have been rebuilt and lost their tracking\n"
        "Companies whose platforms disagree about conversions\n"
        "Anyone who cannot say where their conversions come from",
        "Configured Tag Manager container\n"
        "Pixel and conversion API implementation\n"
        "Conversion events defined and firing correctly\n"
        "Consent banner configured\n"
        "Verification report and documentation",
        "Agree which actions count as conversions and what each is worth\n"
        "Implement the container, tags and events\n"
        "Configure server-side or API tracking where it is warranted\n"
        "Test every event end to end, in the browser and in the platform\n"
        "Document what each number measures, so later arguments are shorter",
        "A verification report confirming each event fires, plus written "
        "documentation.",
    ),
    "conversion-tracking": (
        "Conversion tracking sounds like a technical task and is mostly a "
        "definitional one. Deciding what counts as a conversion — and what "
        "a lead is actually worth to you — determines whether every "
        "optimisation afterwards pushes in the right direction.\n\n"
        "We settle that first, then implement it across every platform so "
        "the numbers reconcile.",
        "Businesses optimising campaigns against the wrong action\n"
        "Companies where ad platforms and analytics disagree\n"
        "Sites with several conversion types of different value\n"
        "Anyone moving from lead volume to lead quality",
        "Agreed conversion definitions and values\n"
        "Events configured across every platform\n"
        "Cross-platform deduplication\n"
        "Verification report\n"
        "Documentation for your team",
        "Run a short workshop on what actually constitutes a conversion\n"
        "Assign values, including for softer actions\n"
        "Configure events consistently across platforms\n"
        "Deduplicate so one action is not counted three times\n"
        "Verify and document",
        "A verification report and documentation, with a follow-up check "
        "after a month of data.",
    ),
    "measurement-audit": (
        "When your analytics, your ad platforms and your sales figures all "
        "disagree, the instinct is to pick the most flattering one. The "
        "better move is to find out why they differ, because the gap is "
        "usually where the money is going.\n\n"
        "We reconcile the numbers and tell you which to trust for which "
        "decision.",
        "Businesses whose reported results do not match revenue\n"
        "Companies with several analytics tools in place\n"
        "Teams unsure which platform's attribution to believe\n"
        "Anyone inheriting a marketing setup they did not build",
        "Tag and data layer review\n"
        "Platform-by-platform discrepancy analysis\n"
        "Attribution model review\n"
        "Remediation plan in priority order",
        "Inventory everything currently measuring anything\n"
        "Compare the same period across every source and quantify the gaps\n"
        "Trace each discrepancy to its cause\n"
        "Assess whether the attribution model matches how you actually sell\n"
        "Deliver the remediation plan",
        "A written audit with a reconciliation table and a fix list.",
    ),
    "reporting-dashboard": (
        "A good dashboard answers the questions you were going to ask "
        "anyway, in one place, without anybody building a slide. A bad one "
        "shows every metric available and answers nothing.\n\n"
        "We build yours around the decisions you actually make, joining "
        "search, ads, social and email into a single view inside your "
        "client workspace.",
        "Businesses pulling numbers from four platforms by hand\n"
        "Companies reporting marketing to a board or an owner\n"
        "Teams running several channels at once\n"
        "Anyone whose monthly reporting takes a day to assemble",
        "Connected data sources\n"
        "Dashboard built to your reporting needs\n"
        "Monthly goals and targets configured\n"
        "Ongoing maintenance as platforms change",
        "Establish which decisions the reporting has to support\n"
        "Connect and validate each data source\n"
        "Build the views, with definitions attached to every metric\n"
        "Set goals so performance reads in context rather than in isolation\n"
        "Maintain it as platforms change their data",
        "The dashboard is the reporting — live in your workspace, with a "
        "monthly summary alongside it.",
    ),
    "digital-marketing-strategy": (
        "The strategy engagement is for businesses who need to decide "
        "where marketing goes next, not just execute the current plan "
        "harder. It covers every channel, the budget across them, the "
        "targets each has to hit and the order to do things in.\n\n"
        "It is deliberately sold on its own. You can take the plan and run "
        "it yourself, give it to another agency, or ask us to execute it — "
        "and it is written to be useful in all three cases.",
        "Businesses at a growth inflection point\n"
        "Companies whose marketing grew channel by channel without a plan\n"
        "New leadership inheriting a marketing function\n"
        "Businesses entering a new market or launching a product line",
        "Business and market discovery findings\n"
        "Channel strategy with budget allocation\n"
        "Targets and the measurement to prove them\n"
        "Twelve-month roadmap in sequence\n"
        "Presentation to your team or board",
        "Discovery across the business, the market and the economics\n"
        "Audit what exists today across every channel\n"
        "Model which channels can deliver at your required cost\n"
        "Set targets and the measurement framework behind them\n"
        "Build the roadmap and present it",
        "A strategy document and a presentation, with an optional quarterly "
        "review.",
    ),
    "campaign-planning": (
        "A launch, a season or a product push touches every channel at "
        "once, and the failure mode is always the same: the channels run "
        "on different timelines with different messages and the assets "
        "arrive late.\n\n"
        "This is the coordinating plan that stops that happening.",
        "Businesses planning a product or service launch\n"
        "Retailers with a significant seasonal peak\n"
        "Companies running an event or a campaign moment\n"
        "Teams coordinating several channels or suppliers",
        "Objective and audience definition\n"
        "Channel plan with messaging per channel\n"
        "Timeline with asset deadlines\n"
        "Measurement framework\n"
        "Post-campaign review",
        "Define the objective in a way that can be measured\n"
        "Identify the audience and the message for each channel\n"
        "Build the timeline backwards from the launch date\n"
        "Schedule every asset with an owner and a deadline\n"
        "Review performance against the objective afterwards",
        "A campaign plan up front and a performance review afterwards.",
    ),
    "performance-review": (
        "Monthly reporting tells you what happened. It is poor at telling "
        "you whether the overall shape of the programme is still right — "
        "that needs a longer view and a willingness to question things "
        "that have become habit.\n\n"
        "Once a quarter, we take that view.",
        "Businesses running marketing across several channels\n"
        "Companies whose budget split has not changed in a year\n"
        "Teams reporting marketing performance upward\n"
        "Anyone wanting an independent view of their programme",
        "Cross-channel performance analysis\n"
        "Review of targets and budget allocation\n"
        "Competitive position check\n"
        "Recommendations for the coming quarter",
        "Gather performance across every channel for the quarter\n"
        "Compare against the targets set and the budget allocated\n"
        "Assess what has changed in the market and the competition\n"
        "Identify what should grow, shrink or stop\n"
        "Present the recommendations",
        "A quarterly review document, presented and discussed.",
    ),
}


#: slug -> [(question, answer), ...]. Only where a service genuinely
#: attracts a question; an invented FAQ is worse than none.
FAQS = {
    "technical-seo-audit": [
        ("Do you fix the issues or just report them?",
         "The audit itself is a report and a walkthrough — we find and "
         "prioritise, your developers implement. We can quote separately "
         "for doing the implementation, and we re-check the fixes once "
         "they ship either way."),
        ("How long does it take?",
         "It depends on the size of the site. A small brochure site is "
         "quick; a large e-commerce catalogue takes considerably longer "
         "because the crawl and the verification both scale with it. We "
         "give you a timeline when we scope it."),
        ("What access do you need?",
         "Read access to Search Console and your analytics, and ideally a "
         "conversation with whoever maintains the site. We can run the "
         "crawl without any access at all, but the findings are weaker."),
    ],
    "seo-growth-retainer": [
        ("How long before we see results?",
         "Search is slow and we will not pretend otherwise. Technical fixes "
         "can move things within weeks; content and authority building "
         "typically take months to compound. We set expectations against "
         "your specific market at the start rather than quoting an industry "
         "average."),
        ("Can we pause the retainer?",
         "Yes, by agreement. We will be straight with you about the cost: "
         "search positions decay when the work stops, and restarting is "
         "more expensive than continuing."),
        ("Do you write the content or do we?",
         "Either. The retainer includes a content plan and briefs; "
         "production can be ours or yours. Clients with a strong in-house "
         "writer often keep that and use us for direction and technical "
         "work."),
    ],
    "google-ads-management": [
        ("Is the ad spend included in the fee?",
         "No. The management fee covers our work; the media spend goes "
         "directly to Google from your own account. You keep ownership of "
         "the account and the data in it."),
        ("What is the minimum budget worth starting with?",
         "It depends entirely on your market's click prices and your deal "
         "value. We would rather tell you honestly at the quote stage that "
         "a budget is too small to learn anything from than take it and "
         "report noise."),
        ("Do we keep the account if we leave?",
         "Yes. We work in your account, not ours. Everything built stays "
         "with you."),
    ],
    "meta-ads-management": [
        ("Do you produce the creative?",
         "We produce the ad copy and the creative direction, and we can "
         "handle production as part of the scope or work with assets you "
         "supply. Creative volume is the main driver of performance here, "
         "so it is worth discussing properly when we scope."),
        ("Will this work with limited tracking?",
         "Partly. We implement the Conversions API to recover what the "
         "browser pixel misses, which helps considerably. Measurement on "
         "Meta is less precise than it was, and we report it that way "
         "rather than presenting modelled numbers as counted ones."),
    ],
    "local-search": [
        ("Can you manage more than one location?",
         "Yes. Multi-location work is scoped on the number of locations, "
         "and the citation clean-up is usually the largest part of it."),
        ("Can you get rid of a bad review?",
         "Only if it breaches the platform's policy, and we will tell you "
         "honestly whether it does. What makes a real difference is "
         "generating enough genuine reviews that one bad one stops being "
         "representative."),
    ],
    "social-media-management": [
        ("How many channels does this cover?",
         "Two as standard. Additional channels are quoted on top, because "
         "doing a third properly costs more than reposting the same "
         "content to it."),
        ("Who approves posts before they go out?",
         "You do. The calendar goes to your workspace for approval before "
         "anything is scheduled, and nothing publishes without sign-off "
         "unless you tell us to stop reviewing."),
    ],
    "creator-partnerships": [
        ("Are creator fees included?",
         "No. Our fee covers sourcing, vetting, briefing, contracting and "
         "measurement. What creators charge is separate and paid to them, "
         "and we negotiate it on your behalf."),
        ("Can we reuse the content in our ads?",
         "Only if the contract says so, which is exactly why we handle the "
         "contracting. Usage rights are one of the most commonly missed "
         "terms in creator agreements and one of the most valuable."),
    ],
    "email-automation-setup": [
        ("Does this include sending the emails?",
         "We build and test the flows in your email platform, and they "
         "send from your account under your sending domain. The setup is "
         "a one-off project; ongoing campaign work is a separate service."),
        ("Which platforms do you work with?",
         "The mainstream ones. Tell us what you use when you enquire and "
         "we will confirm before quoting."),
    ],
    "reporting-dashboard": [
        ("Where does the dashboard live?",
         "In your client workspace on this platform, alongside your "
         "services and approvals. There is no separate login to remember."),
        ("Can we add our own metrics?",
         "Tell us what you need to see and we will build it in, provided "
         "the data source can be connected. Part of the setup is deciding "
         "what belongs on it and what is noise."),
    ],
    "digital-marketing-strategy": [
        ("Do we have to use you to execute the strategy?",
         "No, and it is written on that basis. You can run it in-house, "
         "hand it to another agency, or ask us to deliver parts of it."),
        ("How long does the engagement take?",
         "Discovery and analysis are the bulk of it. We confirm a timeline "
         "when we scope, based on how many channels are in play and how "
         "accessible the existing data is."),
    ],
}


def seed(apps, schema_editor):
    ServiceCategory = apps.get_model("catalog", "ServiceCategory")
    Service = apps.get_model("catalog", "Service")
    ServiceFeature = apps.get_model("catalog", "ServiceFeature")
    ServiceFaq = apps.get_model("catalog", "ServiceFaq")

    now = timezone.now()

    # Strategy had no home in the original five categories.
    strategy, _created = ServiceCategory.objects.get_or_create(
        slug="strategy",
        defaults=dict(
            name="Strategy", order=60,
            short_description="Planning, channel selection and performance "
                              "review.",
            icon="◈", is_visible=True, created_at=now, updated_at=now,
        ),
    )

    categories = {c.slug: c for c in ServiceCategory.objects.all()}
    categories["strategy"] = strategy

    # --- the services the catalogue was missing -----------------------------
    highest = (Service.objects.order_by("-order").values_list("order", flat=True)
               .first() or 0)

    for index, (name, slug, category, description, price, billing,
                featured, features) in enumerate(NEW_SERVICES, start=1):
        if Service.objects.filter(slug=slug).exists():
            continue
        service = Service.objects.create(
            name=name, slug=slug, category=categories[category],
            short_description=description, price=price, currency="USD",
            billing_type=billing, is_featured=featured,
            order=highest + index * 10, is_active=True, is_visible=True,
            created_at=now, updated_at=now,
        )
        for feature_index, label in enumerate(features, start=1):
            ServiceFeature.objects.create(
                service=service, label=label, order=feature_index * 10,
                is_visible=True, created_at=now, updated_at=now,
            )

    # --- the detail that makes a service page worth reading -----------------
    for slug, (full, ideal, deliverables, process, reporting) in DETAIL.items():
        service = Service.objects.filter(slug=slug).first()
        if service is None:
            continue
        # Never overwrite an editor's own words.
        if not service.full_description:
            service.full_description = full
        if not service.ideal_for:
            service.ideal_for = ideal
        if not service.deliverables:
            service.deliverables = deliverables
        if not service.process:
            service.process = process
        if not service.reporting:
            service.reporting = reporting
        service.updated_at = now
        service.save()

    for slug, questions in FAQS.items():
        service = Service.objects.filter(slug=slug).first()
        if service is None or ServiceFaq.objects.filter(service=service).exists():
            continue
        for order, (question, answer) in enumerate(questions, start=1):
            ServiceFaq.objects.create(
                service=service, question=question, answer=answer,
                order=order * 10, is_visible=True,
                created_at=now, updated_at=now,
            )

    # --- category descriptions, now that there are six ----------------------
    descriptions = {
        "search": "Technical SEO, local search, on-page work and content "
                  "planned around real search demand.",
        "paid": "Google, Meta and LinkedIn campaigns managed against cost "
                "per customer rather than clicks.",
        "social": "Publishing, community management, short-form video and "
                  "creator partnerships.",
        "email": "Strategy, automated flows, newsletters and the analysis "
                 "behind them.",
        "analytics": "Tracking that works, conversion measurement you can "
                     "defend, and reporting you can read.",
        "strategy": "Planning, channel selection and performance review.",
    }
    for slug, text in descriptions.items():
        ServiceCategory.objects.filter(slug=slug).update(
            short_description=text, updated_at=now
        )


def unseed(apps, schema_editor):
    """Remove only what this migration added.

    The detail text is left in place: it may have been edited since, and
    there is no way to tell from here.
    """
    Service = apps.get_model("catalog", "Service")
    ServiceCategory = apps.get_model("catalog", "ServiceCategory")
    Service.objects.filter(slug__in=[slug for _, slug, *_ in NEW_SERVICES]).delete()
    ServiceCategory.objects.filter(slug="strategy", services__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [("catalog", "0003_content_fields")]

    operations = [migrations.RunPython(seed, unseed)]
