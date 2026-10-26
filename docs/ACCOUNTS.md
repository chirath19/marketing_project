# Account system

## Status is the only source of truth

`User.status` decides whether an account may sign in. Django's
`is_active` is a **derived, read-only property** (`status == ACTIVE`), not
a second column — two columns that must agree eventually disagree, and
the failure mode is a suspended account that can still log in.

| Status | Can sign in | Meaning |
|---|---|---|
| `pending` | no | Registered, awaiting staff approval |
| `active` | **yes** | Approved |
| `suspended` | no | Temporarily blocked, expected to return |
| `disabled` | no | Closed for good; the row is kept so history survives |

Allowed transitions are declared as data in `services.ALLOWED_TRANSITIONS`;
anything else raises. Status is never changed by assignment — go through
`apps.accounts.services`, which records the timestamp, the reason and
publishes `account.status_changed`.

```python
services.approve_account(user=user, actor=staff, reason="Scoped and signed")
services.suspend_account(user=user, actor=staff, reason="Unpaid invoice")
services.reactivate_account(user=user, actor=staff)
services.disable_account(user=user, actor=staff)
```

## Registration

`ACCOUNTS_REGISTRATION_MODE` (env) selects the workflow:

- **`approval`** (default) — the account is created `PENDING`. The visitor
  sees a page that explains the wait and does *not* promise an email.
  Staff approve from the Django admin (list actions) or, later, the
  dashboard.
- **`auto`** — the account is `ACTIVE` immediately and the visitor is
  signed in.

Approval is the default because there is no email verification in this
version. Automatic activation would mean any address — real, mistyped or
someone else's — gets a live account on an agency platform. It also
matches how the business already works: a client is scoped, priced and
assigned an account manager before anything starts.

## Abuse protection

| Layer | Where |
|---|---|
| Honeypot field | `RegistrationForm.clean_website_url` |
| Rate limit, 5 registrations/hour per address | `REGISTRATION_IP` |
| Rate limit, 20 sign-ins/15 min per address | `LOGIN_IP` |
| Rate limit, 10 sign-ins/15 min per account | `LOGIN_ACCOUNT` |
| Password validators (min 10, not similar to the user's own details) | settings |
| Unique constraint on a normalised email | database |

Rate limiting is **database-backed** (`core.RateLimitEvent`), not cached:
Redis is out of scope, and `DatabaseCache.incr` is a read-then-write with
no lock, so a limit of five can let six through. Counting committed rows
has no such race. Keys are stored as a SECRET_KEY-salted SHA-256 — the
table recognises a repeat caller without identifying one. Run
`manage.py purge_rate_limit_events` periodically.

Both sign-in limits are needed: by address alone, a distributed attempt on
one account slips through; by account alone, one noisy office network
locks out an unrelated user. A successful sign-in clears the account
counter.

## Sign-in messages, without becoming an oracle

The authentication backend stays strict — `authenticate()` returns `None`
for anything that is not `ACTIVE`, so **no** entry point can let a
suspended account through. A strict backend alone would leave a pending
client staring at "please enter a correct email and password" with no way
to find out why, since nothing is emailed.

So on a failed sign-in the form re-checks the password itself and, **only
when it is correct**, explains the status. A wrong password always gets
the generic message, so the form is not an account-existence oracle.

## What is deliberately absent

- **Email verification** — nothing is sent outbound.
- **Password reset by email** — same reason. There is no route for it
  rather than a route that cannot work. A staff-issued, time-limited,
  audited reset surfaced in the Inbox is a later phase.
- **Editing your own email** — it is the login identifier, and with
  nothing outbound there is no way to verify a new address or warn the old
  one, so a typo would silently lock someone out. Staff change it in the
  admin.
- **Staff setting a client's password** — there is no safe way to deliver
  it. `policies.can_change_password` allows only the account holder.

## Who may do what

| Action | Who |
|---|---|
| Edit a profile | the holder, or any staff |
| Change a password | the holder only, knowing the current one |
| Approve / suspend / disable a client | staff, never on themselves |
| Act on a staff or super-admin account | super admin only |
