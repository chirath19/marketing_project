"""Editing website content: who may, and what the controls actually do."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.cms import services
from apps.cms.models import FAQ, NavigationItem, Page, PageSection, PublishStatus
from apps.cms.tests.factories import make_faq, make_page, make_section, make_testimonial
from apps.staff.tests.factories import (
    PASSWORD,
    make_role,
    make_staff_member,
    make_super_admin_user,
)

pytestmark = pytest.mark.django_db


def sign_in(client, user) -> None:  # noqa: ANN001
    assert client.login(username=user.email, password=PASSWORD)


@pytest.fixture
def super_admin():
    return make_super_admin_user()


@pytest.fixture
def editor():
    """Can view, create and edit content — but not publish or delete."""
    return make_staff_member(
        "editor@heliograph.agency",
        roles=[make_role("Editor", ["cms_view", "cms_create", "cms_edit"])],
    )


@pytest.fixture
def viewer():
    return make_staff_member(
        "viewer@heliograph.agency", roles=[make_role("Viewer", ["cms_view"])],
    )


# --- authorisation -----------------------------------------------------------

CONTENT_URLS = ["staff:module_cms", "staff:cms_settings"]


@pytest.mark.parametrize("url_name", CONTENT_URLS)
def test_an_anonymous_visitor_is_sent_to_sign_in(client, url_name):
    response = client.get(reverse(url_name))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.parametrize("url_name", CONTENT_URLS)
def test_a_client_user_is_refused(client, url_name):
    from apps.accounts.tests.factories import make_user

    sign_in(client, make_user(email="client@abc.example"))

    assert client.get(reverse(url_name)).status_code == 403


@pytest.mark.parametrize("url_name", CONTENT_URLS)
def test_staff_without_cms_permissions_are_refused(client, url_name):
    nobody = make_staff_member("nobody@heliograph.agency")
    sign_in(client, nobody.user)

    assert client.get(reverse(url_name)).status_code == 403


def test_a_viewer_can_look_but_not_save(client, viewer):
    page = make_page("Editable", slug="editable")
    sign_in(client, viewer.user)

    assert client.get(reverse("staff:cms_page", args=[page.pk])).status_code == 200
    # cms_edit guards the edit route itself.
    assert client.get(reverse("staff:cms_page_edit", args=[page.pk])).status_code == 403


def test_an_editor_cannot_publish(client, editor):
    """Preparing a page and deciding it is ready are different decisions."""
    page = make_page("Draft", slug="draft", status=PublishStatus.DRAFT)
    sign_in(client, editor.user)

    response = client.post(reverse("staff:cms_page_publish", args=[page.pk]),
                           {"publish": "1"})

    assert response.status_code == 403
    page.refresh_from_db()
    assert page.status == PublishStatus.DRAFT


def test_an_editor_cannot_delete(client, editor):
    page = make_page("Has sections", slug="has-sections")
    section = make_section(page)
    sign_in(client, editor.user)

    response = client.post(reverse("staff:cms_section_delete", args=[section.pk]))

    assert response.status_code == 403
    assert PageSection.objects.filter(pk=section.pk).exists()


def test_a_super_admin_can_publish(client, super_admin):
    page = make_page("Draft", slug="draft2", status=PublishStatus.DRAFT)
    sign_in(client, super_admin)

    client.post(reverse("staff:cms_page_publish", args=[page.pk]), {"publish": "1"})
    page.refresh_from_db()

    assert page.status == PublishStatus.PUBLISHED
    assert page.published_at is not None


def test_the_service_refuses_an_actor_without_the_right(editor):
    page = make_page("Draft", slug="draft3", status=PublishStatus.DRAFT)

    with pytest.raises(PermissionDenied):
        services.publish_page(page=page, actor=editor.user)


# --- ordering and visibility -------------------------------------------------


def test_moving_a_section_swaps_it_with_its_neighbour(super_admin):
    page = make_page("Ordered", slug="ordered2")
    first = make_section(page, body="First", order=10)
    second = make_section(page, body="Second", order=20)

    services.move(instance=second, actor=super_admin, direction="up")
    first.refresh_from_db()
    second.refresh_from_db()

    assert second.order < first.order


def test_moving_the_first_section_up_does_nothing(super_admin):
    page = make_page("Ordered", slug="ordered3")
    first = make_section(page, body="First", order=10)

    services.move(instance=first, actor=super_admin, direction="up")
    first.refresh_from_db()

    assert first.order == 10


def test_moving_only_affects_the_same_page(super_admin):
    """Ordering is scoped, so moving a section on one page cannot
    reshuffle another."""
    page_a = make_page("A", slug="page-a")
    page_b = make_page("B", slug="page-b")
    a_section = make_section(page_a, body="A1", order=10)
    b_section = make_section(page_b, body="B1", order=5)

    services.move(instance=a_section, actor=super_admin, direction="up")
    b_section.refresh_from_db()

    assert b_section.order == 5


def test_hiding_a_section_removes_it_from_the_site(client, super_admin):
    page = make_page("Toggle", slug="toggle")
    section = make_section(page, body="TOGGLE BODY")
    assert b"TOGGLE BODY" in client.get("/toggle/").content

    services.set_visibility(instance=section, actor=super_admin, visible=False)

    assert b"TOGGLE BODY" not in client.get("/toggle/").content


def test_a_viewer_cannot_change_visibility(viewer):
    page = make_page("Toggle", slug="toggle2")
    section = make_section(page)

    with pytest.raises(PermissionDenied):
        services.set_visibility(instance=section, actor=viewer.user, visible=False)


def test_a_new_row_goes_to_the_end_rather_than_colliding_on_zero(client, super_admin):
    from apps.cms.forms import FAQForm

    make_faq(question="First", order=10)
    form = FAQForm(data={"question": "Second", "answer": "Words.",
                         "category": "", "is_visible": True})
    assert form.is_valid(), form.errors

    services.save_object(form=form, actor=super_admin, created=True)

    assert FAQ.objects.order_by("order").last().question == "Second"


# --- the collection screens --------------------------------------------------


COLLECTION_KEYS = ["testimonials", "team", "faqs", "banners", "navigation", "social"]


@pytest.mark.parametrize("key", COLLECTION_KEYS)
def test_every_collection_list_renders(client, super_admin, key):
    sign_in(client, super_admin)

    assert client.get(reverse("staff:cms_collection", args=[key])).status_code == 200


@pytest.mark.parametrize("key", COLLECTION_KEYS)
def test_every_collection_form_renders(client, super_admin, key):
    sign_in(client, super_admin)

    response = client.get(reverse("staff:cms_collection_create", args=[key]))

    assert response.status_code == 200


@pytest.mark.parametrize("key", COLLECTION_KEYS)
def test_a_collection_is_refused_without_permission(client, key):
    nobody = make_staff_member("nobody@heliograph.agency")
    sign_in(client, nobody.user)

    assert client.get(reverse("staff:cms_collection",
                              args=[key])).status_code == 403


def test_an_unknown_collection_is_a_404(client, super_admin):
    sign_in(client, super_admin)

    assert client.get("/staff/cms/not-a-collection/").status_code == 404


def test_creating_a_testimonial_through_the_screen(client, super_admin):
    from apps.cms.models import Testimonial

    sign_in(client, super_admin)

    client.post(reverse("staff:cms_collection_create", args=["testimonials"]), {
        "quote": "They were excellent.", "author_name": "Jo Client",
        "author_role": "", "company": "", "is_visible": "on",
    })

    assert Testimonial.objects.filter(author_name="Jo Client").exists()


def test_deleting_a_row_needs_the_delete_right(client, editor):
    testimonial = make_testimonial(author_name="Stays Put")
    sign_in(client, editor.user)

    response = client.post(
        reverse("staff:cms_collection_delete", args=["testimonials", testimonial.pk])
    )

    assert response.status_code == 403
    assert type(testimonial).objects.filter(pk=testimonial.pk).exists()


# --- the section form --------------------------------------------------------


def test_the_section_form_shows_only_the_fields_its_type_uses():
    """An editor choosing Testimonials should not see a button-link field
    that type ignores."""
    from apps.cms.forms import PageSectionForm

    form = PageSectionForm(initial={"section_type": "testimonials"})

    assert "heading" in form.fields
    assert "cta_url" not in form.fields
    assert "image" not in form.fields


def test_the_hero_form_includes_its_calls_to_action():
    from apps.cms.forms import PageSectionForm

    form = PageSectionForm(initial={"section_type": "hero"})

    assert "cta_label" in form.fields
    assert "secondary_cta_url" in form.fields


def test_the_section_type_cannot_be_changed_once_set():
    """Changing it would leave content in fields the new type ignores,
    which looks like data loss to whoever typed it."""
    from apps.cms.forms import PageSectionForm

    page = make_page("Fixed", slug="fixed")
    section = make_section(page, "hero", heading="Hello")

    form = PageSectionForm(instance=section)

    assert form.fields["section_type"].disabled


def test_a_section_missing_a_required_field_is_refused():
    page = make_page("Invalid", slug="invalid")
    section = PageSection(page=page, section_type="hero", order=10)

    with pytest.raises(ValidationError) as error:
        section.full_clean()

    assert "heading" in error.value.message_dict


def test_an_image_without_a_description_is_refused():
    """An image with no alternative text is invisible to anyone using a
    screen reader, so the CMS will not accept one."""
    page = make_page("Pictures", slug="pictures")
    section = PageSection(page=page, section_type="image_text",
                          heading="Hello", image="cms/sections/x.jpg",
                          image_alt="", order=10)

    with pytest.raises(ValidationError) as error:
        section.full_clean()

    assert "image_alt" in error.value.message_dict


def test_an_unknown_section_type_is_refused():
    page = make_page("Weird", slug="weird")
    section = PageSection(page=page, section_type="teleporter", order=10)

    with pytest.raises(ValidationError):
        section.full_clean()


# --- navigation and settings -------------------------------------------------


def test_a_navigation_item_needs_exactly_one_destination():
    page = make_page("Target", slug="target")

    both = NavigationItem(label="Both", page=page, url="/elsewhere/")
    with pytest.raises(ValidationError):
        both.full_clean()

    neither = NavigationItem(label="Neither")
    with pytest.raises(ValidationError):
        neither.full_clean()


def test_a_navigation_item_linked_to_a_page_follows_its_address():
    page = make_page("Linked", slug="linked")
    item = NavigationItem.objects.create(label="Linked", page=page)

    assert item.href == "/linked/"


def test_site_settings_stay_a_single_row(super_admin):
    from apps.cms.models import SiteSettings

    first = SiteSettings.objects.current()
    SiteSettings.objects.create(site_name="Second attempt")

    assert SiteSettings.objects.count() == 1
    first.refresh_from_db()
    assert first.site_name == "Second attempt"


def test_the_brand_name_comes_from_the_database(client):
    """Not from settings: the agency changes its own name without a deploy."""
    from apps.cms.tests.factories import site_settings

    site_settings(site_name="Renamed Agency")

    assert b"Renamed Agency" in client.get("/").content


# --- pages -------------------------------------------------------------------


def test_only_one_page_of_each_named_kind(super_admin):
    """The seed migration already created one, so "the home page" is
    never ambiguous."""
    assert Page.objects.filter(kind="home").count() == 1

    with pytest.raises(ValidationError, match="already a home page"):
        services.create_page(title="Another home", kind="home", actor=super_admin)


def test_creating_a_page_derives_a_unique_slug(super_admin):
    first = services.create_page(title="Our Work", actor=super_admin)
    second = services.create_page(title="Our Work", actor=super_admin)

    assert first.slug == "our-work"
    assert second.slug == "our-work-2"


def test_creating_a_page_needs_the_create_right(viewer):
    with pytest.raises(PermissionDenied):
        services.create_page(title="Nope", actor=viewer.user)


def test_the_home_page_url_is_the_root():
    page = Page.objects.get(kind="home")

    assert page.get_absolute_url() == "/"


def test_creating_site_settings_updates_the_existing_row_rather_than_raising():
    """`objects.create()` passes force_insert=True, so collapsing to the
    single row needs more than setting the primary key — it raised a
    duplicate key error until both that and `_state.adding` were cleared."""
    from apps.cms.models import SiteSettings

    original = SiteSettings.objects.current()

    SiteSettings.objects.create(site_name="Replaced", tagline="New tagline")

    assert SiteSettings.objects.count() == 1
    original.refresh_from_db()
    assert original.site_name == "Replaced"
    assert original.tagline == "New tagline"
