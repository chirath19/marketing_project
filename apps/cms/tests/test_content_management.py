"""Owner/admin edits reach the public site; content viewers cannot write."""

import pytest
from django.urls import reverse

from apps.accounts.tests.factories import make_user
from apps.cms.forms import ContactPointForm, PageSectionForm
from apps.cms.models import ContactPoint, Page, SectionItem, SiteSettings
from apps.cms.tests.factories import make_item, make_page, make_section
from apps.staff.services import create_staff_account
from apps.staff.tests.factories import PASSWORD, make_role, make_staff_member, make_super_admin_user

pytestmark = pytest.mark.django_db


@pytest.fixture(params=["admin", "owner"])
def content_manager(request, client):
    admin = make_super_admin_user()
    user = admin
    if request.param == "owner":
        user = create_staff_account(
            actor=admin, email="content-owner@example.com", full_name="Owner",
            password=PASSWORD, account_type="system_owner",
        ).user
    client.force_login(user)
    return user


def test_primary_contacts_and_extra_contacts_are_editable(client, content_manager):
    settings = SiteSettings.objects.current()
    original_name = settings.site_name
    response = client.post(reverse("staff:cms_contacts"), {
        "contact_email": "hello@example.com", "contact_phone": "+94 11 234 5678",
        "address_line1": "New office", "city": "Colombo", "response_time_note": "Within two days",
    })
    assert response.status_code == 302
    settings.refresh_from_db()
    assert settings.site_name == original_name
    assert settings.contact_email == "hello@example.com"
    response = client.post(reverse("staff:cms_collection_create", args=["contacts"]), {
        "label": "Support team", "kind": "email", "value": "support@example.com",
        "description": "Weekdays", "is_visible": "on",
    })
    assert response.status_code == 302
    contact = ContactPoint.objects.get(label="Support team")
    listing = client.get(reverse("staff:cms_collection", args=["contacts"]))
    assert listing.status_code == 200 and listing.context["collection"].key == "contacts"
    assert "Support team" in listing.content.decode()
    html = client.get("/contact/").content.decode()
    assert "hello@example.com" in html and "mailto:support@example.com" in html
    assert "New office" in html
    assert "hello@example.com" in client.get("/").content.decode()  # Shared footer.
    assert client.post(reverse("staff:cms_collection_edit", args=["contacts", contact.pk]), {
        "label": "Help desk", "kind": "phone", "value": "+94 11 987 6543",
        "is_visible": "on",
    }).status_code == 302
    html = client.get("/contact/").content.decode()
    assert "Help desk" in html and "tel:+94119876543" in html
    assert "Support team" not in html
    client.post(reverse("staff:cms_collection_toggle", args=["contacts", contact.pk]),
                {"visible": "0"})
    assert "Help desk" not in client.get("/contact/").content.decode()
    client.post(reverse("staff:cms_collection_delete", args=["contacts", contact.pk]))
    assert not ContactPoint.objects.filter(pk=contact.pk).exists()


@pytest.mark.parametrize("kind", ["home", "about"])
def test_edit_and_add_content_on_main_pages(client, content_manager, kind):
    page = Page.objects.get(kind=kind)
    hero = page.sections.filter(section_type="hero").first()
    response = client.post(reverse("staff:cms_section", args=[hero.pk]), {
        "section_type": "hero", "heading": "A new agency story", "tone": "navy",
        "image_alt": hero.image_alt, "is_visible": "on",
        "cta_label": "Talk to our team", "cta_url": "/contact/",
    })
    assert response.status_code == 302
    assert "A new agency story" in client.get(page.get_absolute_url()).content.decode()
    response = client.post(reverse("staff:cms_section_create", args=[page.pk]), {
        "confirm": "1", "section_type": "rich_text", "heading": "Our new chapter",
        "body": "We now work with local creators.", "tone": "light", "is_visible": "on",
    })
    assert response.status_code == 302
    html = client.get(page.get_absolute_url()).content.decode()
    assert "Our new chapter" in html and "We now work with local creators." in html
    section = page.sections.get(heading="Our new chapter")
    client.post(reverse("staff:cms_section_toggle", args=[section.pk]), {"visible": "0"})
    assert "Our new chapter" not in client.get(page.get_absolute_url()).content.decode()


def test_items_can_be_edited_reordered_and_hidden(client, content_manager):
    page = make_page("Our process")
    section = make_section(page, "feature_grid", heading="How we work")
    first = make_item(section, label="First", body="Original description", order=10)
    second = make_item(section, label="Second", order=20)
    other = make_section(make_page("Other"), "stats")
    unrelated = make_item(other, label="Unrelated", order=15)
    response = client.post(reverse("staff:cms_item_edit", args=[first.pk]), {
        "label": "Discovery", "body": "Understand your goals", "is_visible": "on",
    })
    assert response.status_code == 302
    html = client.get(page.get_absolute_url()).content.decode()
    assert "Discovery" in html and "Understand your goals" in html
    client.post(reverse("staff:cms_item_move", args=[first.pk]), {"direction": "down"})
    assert list(section.items.values_list("pk", flat=True)) == [second.pk, first.pk]
    unrelated.refresh_from_db()
    assert unrelated.order == 15
    client.post(reverse("staff:cms_item_toggle", args=[first.pk]), {"visible": "0"})
    assert "Discovery" not in client.get(page.get_absolute_url()).content.decode()
    response = client.post(reverse("staff:cms_item_create", args=[section.pk]), {
        "label": "A" * 121, "body": "Preserve this input", "is_visible": "on",
    })
    assert response.status_code == 200 and response.context["form"].errors
    assert "Preserve this input" in response.content.decode()
    assert not SectionItem.objects.filter(label="A" * 121).exists()
    response = client.post(reverse("staff:cms_item_create", args=[section.pk]), {
        "label": "Launch", "body": "Put the plan into action", "is_visible": "on",
    })
    assert response.status_code == 302
    assert "Put the plan into action" in client.get(page.get_absolute_url()).content.decode()


def test_create_page_draft_then_publish(client, content_manager):
    response = client.post(reverse("staff:cms_page_create"), {
        "title": "Our work", "slug": "our-work", "kind": "standard",
    })
    assert response.status_code == 302
    page = Page.objects.get(slug="our-work")
    assert page.status == "draft"
    assert client.get(page.get_absolute_url()).status_code == 404
    client.post(reverse("staff:cms_section_create", args=[page.pk]), {
        "confirm": "1", "section_type": "rich_text", "heading": "Selected work",
        "body": "Our recent projects", "tone": "light", "is_visible": "on",
    })
    client.post(reverse("staff:cms_page_publish", args=[page.pk]), {"publish": "1"})
    assert "Our recent projects" in client.get(page.get_absolute_url()).content.decode()
    response = client.post(reverse("staff:cms_page_create"), {
        "title": "Wrong address", "slug": "blog", "kind": "standard",
    })
    assert response.status_code == 200 and "slug" in response.context["form"].errors


def test_editor_paths_are_discoverable(client, content_manager):
    page = Page.objects.get(kind="contact")
    home = client.get(reverse("staff:module_cms")).content.decode()
    for label in ["Edit Home page", "Edit About page", "Edit Contact page", "Contact details",
                  "Website wording", "Create page"]:
        assert label in home
    detail = client.get(reverse("staff:cms_page", args=[page.pk])).content.decode()
    assert "Edit primary contact details" in detail and "Add contact" in detail
    for kind in ["team", "testimonials", "faq"]:
        section = make_section(page, kind)
        html = client.get(reverse("staff:cms_section", args=[section.pk])).content.decode()
        assert reverse("staff:cms_collection", args=[section.type_config.collection]) in html


@pytest.mark.parametrize("actor_kind", ["client", "viewer"])
def test_new_write_paths_refuse_unauthorized_users(client, actor_kind):
    user = make_user() if actor_kind == "client" else make_staff_member(
        roles=[make_role("Content viewer", ["cms_view"])],
    ).user
    client.force_login(user)
    section = make_section(make_page(), "stats")
    item = make_item(section, label="Keep me")
    contact = ContactPoint.objects.create(label="Keep contact", kind="other", value="Office hours")
    paths = [
        reverse("staff:cms_contacts"), reverse("staff:cms_page_create"),
        reverse("staff:cms_item_create", args=[section.pk]),
        reverse("staff:cms_item_edit", args=[item.pk]),
        reverse("staff:cms_item_move", args=[item.pk]),
        reverse("staff:cms_item_toggle", args=[item.pk]),
        reverse("staff:cms_collection_edit", args=["contacts", contact.pk]),
        reverse("staff:cms_collection_create", args=["contacts"]),
    ]
    for path in paths:
        response = client.post(path, {"label": "Changed", "kind": "other", "value": "Value"})
        assert response.status_code == 403, path
    item.refresh_from_db()
    contact.refresh_from_db()
    assert item.label == "Keep me" and contact.label == "Keep contact"


@pytest.mark.parametrize("data,field", [
    ({"kind": "email", "value": "not an email"}, "value"),
    ({"kind": "phone", "value": "javascript:alert(1)"}, "value"),
    ({"kind": "other", "value": "Office", "link": "javascript:alert(1)"}, "link"),
    ({"kind": "other", "value": "Office", "link": "ftp://example.com"}, "link"),
])
def test_contact_validation(data, field):
    form = ContactPointForm({"label": "Contact", **data})
    assert not form.is_valid() and field in form.errors


def test_contact_order_and_visibility(client, content_manager):
    a = ContactPoint.objects.create(label="Early office", kind="other", value="Morning", order=10)
    b = ContactPoint.objects.create(label="Late office", kind="other", value="Afternoon", order=20)
    ContactPoint.objects.create(
        label="Private office", kind="other", value="Hidden", is_visible=False,
    )
    client.post(reverse("staff:cms_collection_move", args=["contacts", b.pk]), {"direction": "up"})
    html = client.get("/contact/").content.decode()
    assert html.index(b.label) < html.index(a.label)
    assert "Private office" not in html


def test_home_still_renders_after_removing_hero_image(client, content_manager):
    hero = Page.objects.get(kind="home").sections.get(section_type="hero")
    hero.image = ""
    hero.save()
    assert client.get("/").status_code == 200


def test_type_tampering_does_not_drop_required_fields():
    section = make_section(make_page(), "hero", heading="Heading")
    form = PageSectionForm({"section_type": "stats", "tone": "light"}, instance=section)
    assert not form.is_valid() and "heading" in form.errors


def test_feature_buttons_are_editable_and_unsafe_urls_are_rejected():
    form = PageSectionForm({"section_type": "feature_grid", "heading": "Features",
                           "columns": "3", "tone": "light", "cta_label": "Contact",
                           "cta_url": "javascript:alert(1)"})
    assert "cta_label" in form.fields and "cta_url" in form.fields
    assert not form.is_valid() and "cta_url" in form.errors


def test_items_cannot_be_added_to_non_item_sections(client, content_manager):
    section = make_section(make_page())
    assert client.post(reverse("staff:cms_item_create", args=[section.pk]),
                       {"label": "Invisible content"}).status_code == 404
    assert not section.items.exists()


@pytest.mark.parametrize("label", ["Planning", "01. Planning"])
def test_feature_buttons_saved_in_editor_appear_on_the_site(client, content_manager, label):
    page = make_page("Plan with us")
    section = make_section(page, "feature_grid", heading="Our process")
    make_item(section, label=label)
    response = client.post(reverse("staff:cms_section", args=[section.pk]), {
        "section_type": "feature_grid", "heading": "Our process", "tone": "light",
        "columns": "3", "is_visible": "on", "cta_label": "Discuss your goals",
        "cta_url": "/contact/",
    })
    assert response.status_code == 302
    html = client.get(page.get_absolute_url()).content.decode()
    assert 'href="/contact/"' in html and "Discuss your goals" in html
