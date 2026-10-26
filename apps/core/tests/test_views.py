"""Health endpoint, error pages and the styleguide guard."""

from unittest import mock

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_reports_ok_when_the_database_answers(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"


@pytest.mark.django_db
def test_health_reports_503_when_the_database_is_unreachable(client):
    """A web process that cannot reach Postgres is not ready for traffic;
    returning 200 would let a broken deploy replace a working one."""
    with mock.patch("apps.core.views.connection.cursor", side_effect=OSError("down")):
        response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


@pytest.mark.django_db
def test_health_does_not_leak_error_detail(client):
    with mock.patch(
        "apps.core.views.connection.cursor",
        side_effect=OSError("password=hunter2 host=db.internal"),
    ):
        response = client.get("/healthz")

    assert b"hunter2" not in response.content
    assert b"db.internal" not in response.content


@pytest.mark.django_db
def test_health_is_not_cached(client):
    response = client.get("/healthz")

    assert "no-cache" in response.headers.get("Cache-Control", "")


@pytest.mark.django_db
def test_every_response_carries_a_request_id(client):
    response = client.get("/healthz")

    assert response.headers["X-Request-ID"]


@pytest.mark.django_db
def test_an_inbound_request_id_is_echoed_back(client):
    response = client.get("/healthz", headers={"x-request-id": "abc123"})

    assert response.headers["X-Request-ID"] == "abc123"


@pytest.mark.django_db
def test_an_oversized_request_id_is_truncated(client):
    response = client.get("/healthz", headers={"x-request-id": "z" * 500})

    assert len(response.headers["X-Request-ID"]) == 64


@pytest.mark.django_db
def test_home_page_renders(client):
    response = client.get(reverse("public:home"))

    assert response.status_code == 200
    assert b"Heliograph" in response.content


@pytest.mark.django_db
def test_unknown_url_renders_the_branded_404(client):
    response = client.get("/this-page-does-not-exist/")

    assert response.status_code == 404
    assert b"We could not find that page" in response.content
    # Branded, and useful: somewhere to go rather than only a way back.
    assert b"Browse services" in response.content


@pytest.mark.django_db
def test_styleguide_renders_every_component(client, settings):
    settings.DEBUG = True
    response = client.get(reverse("core:styleguide"))

    assert response.status_code == 200
    for fragment in [b"Design system", b"Deep Navy", b"Live", b"412 of 450",
                     b"Send quote request", b"No campaigns yet"]:
        assert fragment in response.content


@pytest.mark.django_db
def test_styleguide_is_hidden_from_the_public_outside_debug(client, settings):
    """The component inventory is not something an anonymous visitor
    should be able to browse in production."""
    settings.DEBUG = False
    response = client.get(reverse("core:styleguide"))

    assert response.status_code == 404


@pytest.mark.django_db
def test_the_brand_name_survives_a_view_that_sets_its_own_site_name(client):
    """Django's LoginView injects a `site_name` of its own, taken from the
    request host. The brand context is namespaced so that cannot win.

    Asserted against the places the brand is actually printed rather than
    against the whole page: the canonical and Open Graph URLs legitimately
    contain the host, and a blanket search cannot tell those apart from a
    brand name that has been overwritten.
    """
    import re

    body = client.get(reverse("accounts:login")).content.decode()

    title = re.search(r"<title>(.*?)</title>", body, re.DOTALL).group(1)
    assert "Heliograph" in title
    assert "testserver" not in title

    site_name = re.search(r'property="og:site_name" content="([^"]*)"', body)
    assert site_name.group(1) == "Heliograph"


@pytest.mark.django_db
def test_the_brand_context_exposes_every_value_templates_rely_on(client):
    response = client.get(reverse("public:home"))
    brand = response.context["brand"]

    assert set(brand) == {"name", "tagline", "contact_email", "currency", "theme_color"}
    assert brand["name"] == "Heliograph"
