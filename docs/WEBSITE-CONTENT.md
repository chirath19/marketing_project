# Managing website content

Owners and admins can open **Website & content → Pages & website settings** (`/staff/cms/`). Staff can use these tools when their roles grant the corresponding website-content permissions.

## Home, About and Contact

The content dashboard has direct links to these three pages. Open a page, then:

- **Edit** a section to update its heading, text, image, image description and buttons.
- **Add section** to add a text block, feature list, statistics, image and text, team, testimonials, questions, contacts or enquiry form.
- Use the up/down controls to change the order, or **Hide** to keep content without displaying it publicly.
- Feature and statistic entries have their own **Edit**, reorder, **Hide/Show** and **Remove** controls.
- Team, testimonials and question sections link to the shared lists that supply their entries. Changes to a shared list affect every page using that list.

Changes to published pages are visible immediately. New pages start as drafts: add content, publish, then add a link through **Menus & footer links** if needed.

## Contacts

**Contact details** (`/staff/cms/contact-details/`) edits the primary email, telephone, WhatsApp, address and response-time note. These settings also supply the website footer. Leave an optional primary detail empty to remove it.

**Add contact** creates another email address, telephone/WhatsApp number, office address, opening-hours entry or other contact information. Each entry supports a label, description, optional web/map link, order and visibility. **Additional contacts** (`/staff/cms/contacts/`) lists these entries for editing, hiding or removal.

Additional contacts appear alongside the primary details on every page containing a **Contact details** section. They are not client accounts or staff records.

## Shared wording and navigation

**Website wording** edits shared text such as form labels, instructions and footer wording. Page-specific headings and body text remain in the page editor. **Site details** manages the site name, tagline and search/share defaults. **Menus & footer links** manages navigation entries.

## Implementation and deployment

- Added `cms.ContactPoint` through migration `0014_contactpoint`; existing contact settings and page content are preserved.
- Existing CMS create/edit/delete/publish permissions govern the new actions. Clients cannot use these editing tools.
- Added editing, ordering and visibility actions for section items; invalid item forms retain entered values and field errors.
- Feature-grid button fields are now exposed in the editor. Section type stays fixed during editing.
- New-page creation uses the existing draft/publish lifecycle and rejects addresses used by other website routes.
- Removing the Home hero image now uses an existing decorative fallback instead of a missing template.

Run `python manage.py migrate` when deploying and rebuild the stylesheet with `npm run css`. No sample content is inserted by the new migration.
