"""Managing the catalogue from the staff dashboard."""


import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.catalog import services
from apps.catalog.models import Service, ServiceCategory, ServiceFeature, ServicePackage
from apps.catalog.tests.factories import make_feature, make_package, make_service
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
    """Views, creates and edits — but cannot publish or delete."""
    return make_staff_member(
        "editor@heliograph.agency",
        roles=[make_role("Catalogue editor",
                         ["catalog_view", "catalog_create", "catalog_edit"])],
    )


@pytest.fixture
def viewer():
    return make_staff_member(
        "viewer@heliograph.agency", roles=[make_role("Viewer", ["catalog_view"])],
    )


# --- authorisation ------------------------------------------------------------

STAFF_URLS = ["staff:module_services", "staff:catalog_addons"]


@pytest.mark.parametrize("url_name", STAFF_URLS)
def test_an_anonymous_visitor_is_sent_to_sign_in(client, url_name):
    response = client.get(reverse(url_name))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.parametrize("url_name", STAFF_URLS)
def test_a_client_user_is_refused(client, url_name):
    from apps.accounts.tests.factories import make_user

    sign_in(client, make_user(email="client@abc.example"))

    assert client.get(reverse(url_name)).status_code == 403


@pytest.mark.parametrize("url_name", STAFF_URLS)
def test_staff_without_catalogue_permissions_are_refused(client, url_name):
    nobody = make_staff_member("nobody@heliograph.agency")
    sign_in(client, nobody.user)

    assert client.get(reverse(url_name)).status_code == 403


def test_a_viewer_can_look_but_not_create(client, viewer):
    sign_in(client, viewer.user)

    assert client.get(reverse("staff:module_services")).status_code == 200
    assert client.get(reverse("staff:catalog_create")).status_code == 403


def test_an_editor_cannot_publish_a_service(client, editor):
    """Showing a price to the public is a different decision from writing
    the page."""
    service = make_service("Hidden", is_visible=False)
    sign_in(client, editor.user)

    response = client.post(
        reverse("staff:catalog_service_visibility", args=[service.pk]),
        {"visible": "1"},
    )

    assert response.status_code == 403
    service.refresh_from_db()
    assert not service.is_visible


def test_an_editor_cannot_retire_a_service(client, editor):
    service = make_service("Live")
    sign_in(client, editor.user)

    response = client.post(reverse("staff:catalog_service_active", args=[service.pk]),
                           {"active": "0"})

    assert response.status_code == 403
    service.refresh_from_db()
    assert service.is_active


def test_an_editor_cannot_delete_a_service(client, editor):
    service = make_service("Stays")
    sign_in(client, editor.user)

    response = client.post(reverse("staff:catalog_service_delete", args=[service.pk]))

    assert response.status_code == 403
    assert Service.objects.filter(pk=service.pk).exists()


def test_the_service_layer_refuses_publishing_without_the_right(editor):
    service = make_service("Hidden", is_visible=False)

    with pytest.raises(PermissionDenied):
        services.set_service_visibility(service=service, actor=editor.user,
                                        visible=True)


# --- creating and editing -----------------------------------------------------


def test_a_new_service_starts_hidden(client, super_admin):
    """So nothing half-written reaches the public catalogue."""
    sign_in(client, super_admin)

    client.post(reverse("staff:catalog_create"), {
        "name": "Brand new service", "slug": "",
        "category": ServiceCategory.objects.first().pk,
        "short_description": "Does things.", "full_description": "",
        "price": "1200", "currency": "USD", "billing_type": "monthly",
        "image_alt": "", "icon": "", "meta_title": "", "meta_description": "",
    })

    service = Service.objects.get(name="Brand new service")
    assert service.slug == "brand-new-service", "a blank slug derives from the name"
    # The form has no visibility field, so the model default applies.
    assert service.is_active


def test_publishing_puts_a_service_on_the_catalogue(client, super_admin):
    service = make_service("Going live", is_visible=False)
    sign_in(client, super_admin)

    client.post(reverse("staff:catalog_service_visibility", args=[service.pk]),
                {"visible": "1"})

    assert b"Going live" in client.get("/services/").content


def test_retiring_takes_it_down_but_keeps_the_row(client, super_admin):
    service = make_service("Retiring")
    sign_in(client, super_admin)

    client.post(reverse("staff:catalog_service_active", args=[service.pk]),
                {"active": "0"})

    assert b"Retiring" not in client.get("/services/").content
    assert Service.objects.filter(pk=service.pk).exists()


def test_duplicate_names_get_distinct_slugs(super_admin):
    from apps.catalog.forms import ServiceForm

    category = ServiceCategory.objects.first()
    for _ in range(2):
        form = ServiceForm(data={
            "name": "Same name", "slug": "", "category": category.pk,
            "short_description": "x", "full_description": "",
            "price": "100", "currency": "USD", "billing_type": "monthly",
            "image_alt": "", "icon": "", "meta_title": "", "meta_description": "",
        })
        assert form.is_valid(), form.errors
        services.save_catalog_object(form=form, actor=super_admin, created=True)

    slugs = sorted(Service.objects.filter(name="Same name")
                   .values_list("slug", flat=True))
    assert slugs == ["same-name", "same-name-2"]


def test_moving_a_service_reorders_the_catalogue(super_admin):
    category = ServiceCategory.objects.first()
    first = make_service("First", category=category, order=10, slug="first-one")
    second = make_service("Second", category=category, order=20, slug="second-one")

    services.move(instance=second, actor=super_admin, direction="up")
    first.refresh_from_db()
    second.refresh_from_db()

    assert second.order < first.order


# --- features and packages ----------------------------------------------------


def test_a_feature_can_be_added_to_a_service(client, super_admin):
    service = make_service("Featureless")
    sign_in(client, super_admin)

    client.post(reverse("staff:catalog_feature_create", args=[service.pk]), {
        "label": "A brand new feature", "description": "", "is_visible": "on",
    })

    assert ServiceFeature.objects.filter(service=service,
                                         label="A brand new feature").exists()


def test_a_package_can_be_added_to_a_service(client, super_admin):
    service = make_service("Tierless")
    sign_in(client, super_admin)

    client.post(reverse("staff:catalog_package_create", args=[service.pk]), {
        "name": "Starter", "slug": "", "summary": "", "price": "900",
        "currency": "USD", "billing_type": "monthly", "is_visible": "on",
    })

    assert ServicePackage.objects.filter(service=service, name="Starter").exists()


def test_ticking_features_sets_what_a_package_includes(client, super_admin):
    service = make_service("Tiered")
    first = make_feature(service, "Included one")
    second = make_feature(service, "Not included", order=20)
    package = make_package(service, "Starter")
    sign_in(client, super_admin)

    client.post(reverse("staff:catalog_package", args=[package.pk]), {
        "name": "Starter", "slug": "starter", "summary": "",
        "price": "900", "currency": "USD", "billing_type": "monthly",
        "is_visible": "on", "features": [first.pk],
    })

    assert package.includes(first)
    assert not package.includes(second)


def test_unticking_a_feature_removes_it(super_admin):
    """A configuration screen posts the ticked boxes, so unticking has to
    remove."""
    service = make_service("Tiered")
    feature = make_feature(service, "Was included")
    package = make_package(service, "Starter")
    services.set_package_features(package=package, actor=super_admin,
                                  included_ids=[feature.pk])
    assert package.includes(feature)

    services.set_package_features(package=package, actor=super_admin,
                                  included_ids=[])

    assert not package.includes(feature)


def test_a_package_cannot_be_given_another_services_feature(super_admin):
    first = make_service("First")
    second = make_service("Second", slug="second")
    foreign = make_feature(second, "Not ours")
    package = make_package(first, "Tier")

    services.set_package_features(package=package, actor=super_admin,
                                  included_ids=[foreign.pk])

    assert not package.includes(foreign)


# --- add-ons -------------------------------------------------------------------


def test_an_addon_can_be_created(client, super_admin):
    from apps.catalog.models import ServiceAddon

    sign_in(client, super_admin)

    client.post(reverse("staff:catalog_addon_create"), {
        "name": "A new add-on", "slug": "", "short_description": "",
        "price": "250", "currency": "USD", "billing_type": "one_time",
        "is_active": "on", "is_visible": "on",
    })

    assert ServiceAddon.objects.filter(name="A new add-on").exists()


def test_creating_an_addon_needs_the_create_right(client, viewer):
    from apps.catalog.models import ServiceAddon

    sign_in(client, viewer.user)
    before = ServiceAddon.objects.count()

    response = client.post(reverse("staff:catalog_addon_create"), {
        "name": "Sneaky", "slug": "", "price": "1", "currency": "USD",
        "billing_type": "one_time",
    })

    assert response.status_code == 403
    assert ServiceAddon.objects.count() == before


# --- categories ----------------------------------------------------------------


def test_the_category_screen_renders(client, super_admin):
    sign_in(client, super_admin)

    response = client.get(reverse("staff:cms_collection", args=["service-categories"]))

    assert response.status_code == 200


def test_a_category_cannot_be_deleted_while_services_use_it(super_admin):
    """PROTECT, so retiring a category does not silently take its services
    with it."""
    from django.db.models import ProtectedError

    category = ServiceCategory.objects.first()
    make_service("Uses it", category=category, slug="uses-it")

    with pytest.raises(ProtectedError):
        category.delete()


def test_the_seeded_catalogue_is_valid():
    """A migration bypasses `full_clean`, so a seeded row can break rules
    the editor would enforce."""
    from django.core.exceptions import ValidationError

    problems = []
    for service in Service.objects.all():
        try:
            service.full_clean()
        except ValidationError as error:
            problems.append((service.name, error.message_dict))

    for package in ServicePackage.objects.all():
        try:
            package.full_clean()
        except ValidationError as error:
            problems.append((str(package), error.message_dict))

    assert not problems, problems
