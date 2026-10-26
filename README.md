# Heliograph platform

Digital marketing agency platform: public site, CMS, service catalogue,
client portal and staff back office. Django modular monolith on
PostgreSQL, server-rendered with Tailwind + HTMX, deployable to Railway.

Architecture and phase plan: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status

Phases 1 (foundation), 2 (design system), 3 (accounts), 4 (client
organizations), 5 (staff access control), 6 (admin dashboard shell) and
7 (CMS and public website), 8 (blog), 9 (service catalogue),
10 (leads, contacts and the Inbox), the content and polish pass, and
11 (the quote request workflow), 12 (client service subscriptions) and
13 (the dynamic client portal), 14 (the campaign engine), 15 (SEO),
16 (Paid Ads), 17 (Social Media), 18 (Email Marketing client service), and
19 (shared client approvals) are implemented. The platform has 21 domain apps; several later delivery, communication
and governance modules remain scaffolded.

The Approvals workspace unifies campaign and deliverable decisions, client/staff
comments, permanent history and in-app notifications. Pending counts appear on the
staff and client dashboards. No email or SMS is sent. See
[docs/APPROVALS.md](docs/APPROVALS.md).

The Email Marketing workspace manages client campaign work, newsletters, automation
flow plans, versioned deliverables, approvals and manually recorded daily results.
It sends no email and has no outbound provider integration. See
[docs/EMAIL-MARKETING.md](docs/EMAIL-MARKETING.md).

The Social Media workspace supports content schedules, creator partnerships,
versioned deliverables and client approvals, and manually recorded daily results.
It does not post to social platforms. See [docs/SOCIAL-MEDIA.md](docs/SOCIAL-MEDIA.md).

The Paid Ads workspace supports daily campaign/platform observations,
manual entry and CSV import, date/platform/campaign/currency filters,
calculated KPIs, performance tables and dated goals. See
[docs/PAID-ADS.md](docs/PAID-ADS.md) for the workflow and import format.

The component library is documented in
[docs/DESIGN-SYSTEM.md](docs/DESIGN-SYSTEM.md) and rendered live at
`/styleguide/`. The account system — statuses, registration modes and
abuse protection — is in [docs/ACCOUNTS.md](docs/ACCOUNTS.md), and the
tenancy model in [docs/ORGANIZATIONS.md](docs/ORGANIZATIONS.md). Roles,
permissions and client assignments are in
[docs/PERMISSIONS.md](docs/PERMISSIONS.md), and the staff dashboard shell
in [docs/ADMIN-DASHBOARD.md](docs/ADMIN-DASHBOARD.md). The CMS and public
site are in [docs/CMS.md](docs/CMS.md), and the blog in
[docs/BLOG.md](docs/BLOG.md). The service catalogue is in
[docs/CATALOGUE.md](docs/CATALOGUE.md), leads and the Inbox in
[docs/LEADS.md](docs/LEADS.md), quote requests in
[docs/QUOTES.md](docs/QUOTES.md), client services in
[docs/SUBSCRIPTIONS.md](docs/SUBSCRIPTIONS.md), the client portal in
[docs/PORTAL.md](docs/PORTAL.md), campaigns in
[docs/CAMPAIGNS.md](docs/CAMPAIGNS.md), and what the site says — and who can
change it — in [docs/CONTENT.md](docs/CONTENT.md).

## Requirements

Docker, for the quickest start. For working without it: Python 3.12+
(3.14 here) and Node 20+ (build-time only, for Tailwind).

## Run it with Docker

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"   # paste into DJANGO_SECRET_KEY

docker compose up --build        # → http://localhost:8000
```

The entrypoint waits for PostgreSQL, applies migrations and creates the
cache table, so a clean machine needs no second command. Source is mounted,
so edits reload live.

| | |
|---|---|
| Public site | http://localhost:8000 |
| Health | http://localhost:8000/healthz |
| Styleguide | http://localhost:8000/styleguide/ |
| Staff dashboard | http://localhost:8000/staff/dashboard/ |
| Django admin (developers) | http://localhost:8000/admin/ |
| PostgreSQL | `localhost:5432` (heliograph / heliograph) |

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web pytest
docker compose logs -f web
docker compose down              # add -v to drop the database volume
```

**Careful with `$` in `.env`.** Docker Compose interpolates it when reading
the file, so a secret containing one is silently mangled and the container
ends up with a different value than the host. Generate keys with
`secrets.token_urlsafe()`, or escape a literal `$` as `$$`.

The image runs gunicorn by default, matching the Procfile that Railway
uses; Compose overrides it with the dev server for the auto-reload.

## Local setup (without Docker)

```bash
python -m venv venv
./venv/bin/pip install -r requirements/dev.txt
npm install

cp .env.example .env
# Generate a key and paste it into DJANGO_SECRET_KEY:
./venv/bin/python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"

make db-up          # PostgreSQL 17 on :5432
make migrate        # migrations + cache table
make css            # build static/dist/app.css
make run            # http://127.0.0.1:8000
```

`make help` lists every task.

Create an administrator:

```bash
./venv/bin/python manage.py createsuperuser
```

## Checks

```bash
make check    # system checks, plus --deploy against production settings
make test     # pytest
make lint     # ruff
```

## Layout

```
config/settings/   base, dev, prod, test — all values from the environment
apps/<domain>/     models, selectors (reads), services (writes), policies (authz)
templates/         base layouts, shared components, public pages, error pages
assets/css/        Tailwind source  →  static/dist/app.css (committed)
static/vendor/     HTMX and Alpine, self-hosted
requirements/      base, dev, prod
```

Conventions that tests enforce (`tests/`):

- Views and serializers never import another domain's models — they go
  through that domain's selectors and services.
- Domains communicate through the core event bus, not direct imports.
- No Redis, no Celery, no SMTP or other outbound messaging provider.
- No secret in source; `.env` is git-ignored.
- No multi-line `{# … #}` in templates (Django renders those to the page).
- No raw hex colours in templates — tokens only.
- No component leaks page context when an argument is omitted.
- Every model in a tenant domain belongs to an organization.
- `visible_to` is defined only in the organizations domain.
- Every view in a guarded module declares a permission.
- Every DRF view declares `permission_classes`.
- Every navigation item points at a guarded route whose permission exists.

## Deployment

Railway. Set the variables from `.env.example` as service variables, add a
PostgreSQL service (`DATABASE_URL` is injected), and set
`DJANGO_SETTINGS_MODULE=config.settings.prod`. `railway.toml` runs
`collectstatic` at build and the `Procfile` release phase runs migrations
before the new version takes traffic. Healthcheck: `/healthz`.

## Messaging

This version sends nothing outbound — no email, SMS or WhatsApp. Every
enquiry, quote request, approval and system alert is stored in PostgreSQL
and shown in the in-app Inbox and Notification Center. The mail backend is
console in development and a discarding backend in production, so a stray
`send_mail` cannot deliver. Adding a provider later means writing a
channel adapter and registering it; the core does not change.
