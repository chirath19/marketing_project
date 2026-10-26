# Client organizations

## A client company is never a user

```
ABC Holdings                      Organization
├── Ann Owner       owner         OrganizationMember
├── Mo Marketing    admin         OrganizationMember
└── Fay Finance     viewer        OrganizationMember
```

Everything the platform produces for a client — campaigns, subscriptions,
reports, approvals, messages — belongs to the **Organization**. A person
leaving does not take the work with them, and a second person from the
same company joins the company rather than starting a new one.

## Models

**`Organization`** — legal `name`, optional `display_name` (trading name),
unique `slug` for URLs, `website`, `email`, `phone`, a full postal address
(`address_line1/2`, `city`, `region`, `postal_code`, `country`), `status`,
staff-only `notes`, and timestamps from `TimeStampedModel`.

| Status | Meaning |
|---|---|
| `pending` | Created, not yet onboarded |
| `active` | Live; work can be delivered |
| `suspended` | Temporarily stopped |
| `archived` | Relationship ended. Kept, never deleted |

**`OrganizationMember`** — joins `user` to `organization` with a `role`
and a `status`, plus `job_title` and who added them. One membership per
person per organization, enforced by a unique constraint: two rows would
mean two answers to "what may they do here".

| Role | |
|---|---|
| `owner` | Everything, including removing other members |
| `admin` | Manages people and settings, approves work |
| `member` | Day-to-day use |
| `viewer` | Read-only — a finance contact, an exec who wants the numbers |

Member status is `active` / `suspended` / `removed`. Removal keeps the row
so the approvals and messages attributed to that person keep their author.

## Isolation

`OrganizationOwnedModel` is the base every tenant-owned model inherits:

```python
class Campaign(OrganizationOwnedModel, TimeStampedModel):
    ...                      # organization FK and scoping come for free

Campaign.objects.visible_to(request.user)
```

`visible_to` is defined **once**, on `OrganizationOwnedQuerySet`: staff see
everything, a client sees only rows belonging to an organization they
actively belong to. A test fails the build if a second definition appears
anywhere outside this domain.

`organization` uses `on_delete=PROTECT`, so deleting a company that still
has work attached fails loudly rather than quietly taking the history with
it. Archive instead.

Two more guards, in `tests/test_architecture.py`:

- every concrete model in a tenant domain must inherit the base, or relate
  to something that does;
- a new organization-owned model must be added to `TENANT_MODELS` in the
  isolation matrix, so it cannot ship without coverage.

## The current organization

`request.organization` is resolved **server-side from the signed-in user's
memberships** by `CurrentOrganizationMiddleware` — never from a path
segment, query parameter or header. A slug in a request is an intention,
not an entitlement. The chosen organization is re-checked against live
membership on every request, so writing another company's id into the
session grants nothing.

It is a lazy proxy, so pages that never mention an organization cost no
query. **Test it with `has_organization(request)` or truthiness, never
`is None`** — a `SimpleLazyObject` wrapping None is still an object, and a
guard written that way silently lets staff into client code paths.

Staff are not members of client companies, so `request.organization` is
empty for them; staff views resolve the organization from the URL through
`selectors.get_organization`, which only returns what that actor may see.
An organization that belongs to someone else produces a **404, not a 403** —
confirming it exists is itself information.

## Onboarding

Registration creates the organization and makes the registrant its owner.
If the company name was left blank the account is still created, and the
`/organization/setup/` page asks on first sign-in — a missing company name
is not a reason to lose a registration. Anyone who already belongs
somewhere is redirected away from that page, so it cannot be used to spawn
extra organizations.

There are no email invitations: nothing is sent outbound. An owner or admin
adds a colleague by email on the People page, and the person must already
have an account. The form says so plainly rather than silently doing
nothing.

## Rules worth knowing

- **Nobody promotes themselves.** An admin cannot make themselves an owner.
- **The last owner cannot be demoted or removed.** An organization with
  nobody in charge cannot add members or change its own details; it would
  need staff to recover.
- **Only staff change an organization's status.** It is a commercial
  control; a client lifting their own suspension would make it meaningless.
- **Internal notes are staff-only in both directions** — a client may
  neither write them nor read them.
