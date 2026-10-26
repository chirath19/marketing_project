# Workflow dashboard redesign

The Client, Owner and Admin dashboards now follow the quotation-to-project journey. Existing domain models, routes, forms, feature switches and authorization policies remain in place. This change requires no database migration.

## Navigation

| Audience | Primary areas |
| --- | --- |
| Client | Overview, Requests & quotes, Projects & services, Messages, Payments, Account |
| Owner / Admin | Dashboard, Clients, Requests & quotes, Projects & services, Messages, Payments, Website & content, Team & administration |
| Restricted staff | Only the workflow areas containing tools they can access |

The capability registries in `apps/staff/navigation.py` and `apps/core/modules.py` remain the source of available tools and entitlements. `apps/core/workflow.py` organizes permitted tools into workflow areas. It does not grant permissions. Existing module URLs continue to enforce their own guards.

Staff workflow entry points are `/staff/workspace/requests/`, `/staff/workspace/projects/`, `/staff/workspace/payments/`, `/staff/workspace/website/` and `/staff/workspace/administration/`.

## Client journey

1. **Overview** puts the next decision or reply before totals. New clients receive an explanation and a quotation action instead of empty metric tiles.
2. **Requests & quotes** contains quotations and secondary access to renewals or extra work. Quotation detail explains the current stage and next action, alongside the existing scope, decisions and conversation.
3. **Projects & services** lists current, pending and finished work. Opening a project shows its progress reports, files, next steps, relevant client reviews, requested changes, invoices and receipts. Specialist results are accessed from that project. Work shared across projects remains available in a collapsed section.
4. **Messages** opens the private account-team conversation. Starting from a project preselects that project in the message composer.
5. **Payments** groups invoices and balances with receipts. Existing printing and receipt corrections remain available through authorized screens.
6. **Account** groups company details, people/access and personal profile links. Clients with multiple memberships retain a company switcher.

Progress percentages come from manually published reports. A project with no report says so; no percentage is inferred from its status. Invoice payment status and balances continue to use actual invoice and receipt records.

## Owner and Admin journey

- **Dashboard** prioritizes new requests, upcoming deadlines, messages and named work waiting on a client decision. Less common totals are collapsed.
- **Clients → a client** opens a combined workspace for projects, paginated quotations, client reviews, progress/files, conversations, invoices and receipts. A contact selection keeps private records separate when a company has multiple client users.
- **Requests & quotes** shows recent requests and entry points for quotation preparation, enquiries, follow-up and renewals/extra work.
- **Projects & services** provides current work and progress-update entry points. Specialist modules and review tools are grouped below everyday work. Project detail connects the actual campaign work and preselects the project when opening reporting, conversation or billing forms. Commercial editing is disclosed separately.
- **Payments** selects a client recipient before managing invoices and receipts.
- **Website & content** groups page/site editing, the catalogue, blog and the existing media placeholder.
- **Team & administration** groups staff accounts, roles, settings, integrations, analytics and the existing audit placeholder. Planned tools retain their labels as planned; the redesign does not imply those tools are implemented.

Owner and Admin share the information architecture while retaining distinct rights. The existing Admin-only operating-settings restriction remains intact.

## Privacy and preserved behavior

- Every composed workspace reads through existing scoped selectors and policies.
- Client projects are scoped to the selected company. Quotations include that company's requests and the signed-in client's own unlinked requests.
- Reports, invoices and receipts remain tied to their named recipient. Another member of the same company cannot see these through a shared project.
- Unpublished reports stay hidden from clients. Internal service events remain filtered out.
- Client-contact selection rejects contacts outside the selected company. Project context rejects projects from another company.
- Feature switches continue hiding disabled functionality. Manual reports remain independent of automated analytics.
- Notification bells, unread highlights, live badge updates, message polling, CSRF protection and existing business transitions remain in place.
- No automatic posting, outbound emails, SMS, payment collection or new provider integration is introduced.

## Verification

- Complete regression suite: **2,358 passed, 2 existing skips**.
- New workflow tests cover navigation, role restrictions, recipient isolation, disabled features, company switching, project message context and quote-linked payment records.
- Django system check: no issues. Migration check: no changes.
- Ruff and JavaScript syntax checks pass; production CSS rebuilt.
- Chromium checks cover **34 desktop/mobile surfaces** at 1440px and 390px across Client, Owner and Admin. No horizontal overflow, page JavaScript errors or automated WCAG A/AA violations were found in these checks. Automated checks are not a substitute for a complete manual accessibility audit.
- Browser interaction verifies Owner publication of a project report, Client visibility of the update, project-prefilled messaging and successful message submission.

Screenshots and the accessibility results are in [workflow-redesign](workflow-redesign/). Screenshot records are synthetic preview data created in an isolated test database, not live client or advertising data.
