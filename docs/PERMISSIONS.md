# Staff access control

## The rule

```
permission to perform the action
AND
access to the client organization
```

Neither half alone is authorisation. An SEO specialist with `seo_edit`
can edit SEO campaigns — for the clients they are assigned to, and no
others.

One function answers it, `apps/permissions/access.py::can()`, and
everything else calls that: the view decorator, the class-based mixin, the
DRF permission class, the export filter, and `user.has_perm()`.

## Built on Django, not around it

Granular rights are real `django.contrib.auth.Permission` rows, generated
from `apps/permissions/catalogue.py` (97 permissions across 19 modules).
That means `user.has_perm("permissions.seo_edit", obj)`,
`{% if perms.permissions.seo_edit %}`, `@permission_required` and DRF all
work unmodified.

Three things Django does not provide are added rather than reinvented:

| | |
|---|---|
| **Role** | A named bundle of permissions. Not `auth.Group`, because a Group is resolved by Django's own backend, which knows nothing about deny or client scoping. |
| **RolePermission** | An explicit through model, so a grant records who made it and when. |
| **UserPermissionOverride** | Grant *or* **deny**, per person. |

**There is exactly one authentication backend**, and a test enforces it.
Django resolves `has_perm` as a union across backends — anything that
grants wins — so a second backend could re-grant a permission this
platform denies. `PlatformPermissionBackend` subclasses `ModelBackend`, so
authentication and Django's own model permissions (which the admin needs)
behave exactly as before.

## Resolution order

```
1. deny override      beats everything, including every role
2. grant override     a personal exception a role cannot express
3. role permissions   the usual path
4. otherwise denied   the default is closed
```

A super admin holds everything; a client holds no platform permissions at
all (their rights come from organization membership, a different
mechanism). Results are memoised per user object for the life of the
request; the services that change roles, overrides or assignments clear
that cache so a change lands immediately.

## Actions

`view` · `create` · `edit` · `delete` · `publish` · `approve` · `assign` ·
`export` · `manage`

Not every module takes every action — the catalogue declares which pairs
exist, and an unknown codename is refused rather than silently ignored, so
a typo cannot produce a role with fewer rights than whoever configured it
believed.

Modules are either **client-scoped** (campaigns, seo, paid_ads, social,
email_marketing, analytics, approvals, messaging, media, leads,
subscriptions, organizations) or **platform-wide** (catalog, cms, staff,
roles, settings, integrations, audit). An unknown permission is treated as
client-scoped: the safer answer is the one that restricts.

## Models

| | |
|---|---|
| `staff.StaffProfile` | Roles, department, `has_all_client_access` |
| `staff.StaffClientAssignment` | Staff ↔ client, with an on-account role, status and primary-contact flag |
| `permissions.Role` / `RolePermission` | The bundles |
| `permissions.UserPermissionOverride` | Per-person grant or deny |

Seven system roles ship in a migration: Account Manager, SEO Specialist,
Paid Ads Specialist, Social Media Manager, Analyst, Content Editor,
Operations Manager. They can be edited but not deleted.

## Guarding an endpoint

```python
@require_permission("seo_edit")                       # permission only
@require_permission("organizations_view", lookup=_organization)   # + client
```

The `lookup` form resolves the object first and checks the permission
*against it* — that is what makes an object endpoint safe.

For lists, exports and API collections, **two guards are needed**:

```python
@require_permission("organizations_export")           # may they export?
clients = scope_to_accessible(qs, request.user)       # export what?
```

A permission check cannot filter rows. An export without the second guard
hands an unassigned specialist the entire client book in one click —
around every object-level check at once.

For DRF, `HasPlatformPermission` with `required_permissions` mapped per
method; the queryset must still be scoped, because DRF only calls
`has_object_permission` on detail routes.

## 403 or 404

Both appear, deliberately:

- **403** — staff who can see that other clients exist, being refused one.
- **404** — a client, or someone without permission to list at all.
  Confirming the record exists would itself be a leak, so the selector
  does not return it and the view never gets that far.

## Guards that outlive this phase

In `tests/test_architecture.py`:

- every view in a guarded module must carry `@require_permission` (or be
  listed in `UNGUARDED_VIEWS` **with a reason** — the point is that it is
  a decision, not an omission);
- every DRF view must declare `permission_classes`, since the project
  default is only `IsAuthenticated`;
- `require_permission` may be defined only in the permissions domain.
