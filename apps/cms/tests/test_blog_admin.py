"""Managing the blog from the staff dashboard."""

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from apps.cms import services
from apps.cms.models import BlogPost, Category, PublishStatus, Tag
from apps.cms.tests.factories import make_category, make_post, make_tag
from apps.staff.tests.factories import (
    PASSWORD,
    make_role,
    make_staff_member,
    make_super_admin_user,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _blog_starts_empty():
    """Clear the seeded articles before each test in this module.

    A migration seeds four articles so a fresh install does not launch
    with an empty blog. These tests state their own fixtures and assert
    on ordering, filtering and counts — the seeded rows would quietly
    join every one of those assertions.
    """
    from apps.cms.models import BlogPost, Category, Tag

    BlogPost.objects.all().delete()
    Category.objects.all().delete()
    Tag.objects.all().delete()


def sign_in(client, user) -> None:  # noqa: ANN001
    assert client.login(username=user.email, password=PASSWORD)


@pytest.fixture
def super_admin():
    return make_super_admin_user()


@pytest.fixture
def writer():
    """Writes and edits posts, but cannot publish or delete them."""
    return make_staff_member(
        "writer@heliograph.agency",
        roles=[make_role("Writer", ["blog_view", "blog_create", "blog_edit"])],
    )


@pytest.fixture
def nobody():
    return make_staff_member("nobody@heliograph.agency")


# --- authorisation -----------------------------------------------------------


def test_an_anonymous_visitor_is_sent_to_sign_in(client):
    response = client.get(reverse("staff:module_blog"))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


def test_a_client_user_is_refused(client):
    from apps.accounts.tests.factories import make_user

    sign_in(client, make_user(email="client@abc.example"))

    assert client.get(reverse("staff:module_blog")).status_code == 403


def test_staff_without_blog_permissions_are_refused(client, nobody):
    sign_in(client, nobody.user)

    assert client.get(reverse("staff:module_blog")).status_code == 403


def test_cms_permissions_alone_do_not_open_the_blog(client):
    """Writing articles and editing marketing pages are different jobs,
    so an agency can grant one without the other."""
    editor = make_staff_member(
        "pages@heliograph.agency",
        roles=[make_role("Pages only", ["cms_view", "cms_edit", "cms_publish"])],
    )
    sign_in(client, editor.user)

    assert client.get(reverse("staff:module_blog")).status_code == 403


def test_a_writer_can_open_the_blog(client, writer):
    sign_in(client, writer.user)

    assert client.get(reverse("staff:module_blog")).status_code == 200


def test_a_writer_cannot_publish(client, writer):
    post = make_post("Draft post", published=False)
    sign_in(client, writer.user)

    response = client.post(reverse("staff:blog_publish", args=[post.pk]),
                           {"publish": "1"})

    assert response.status_code == 403
    post.refresh_from_db()
    assert post.status == PublishStatus.DRAFT


def test_a_writer_cannot_delete(client, writer):
    post = make_post("Stays put")
    sign_in(client, writer.user)

    response = client.post(reverse("staff:blog_delete", args=[post.pk]))

    assert response.status_code == 403
    assert BlogPost.objects.filter(pk=post.pk).exists()


def test_the_service_refuses_publishing_without_the_right(writer):
    post = make_post("Draft", published=False)

    with pytest.raises(PermissionDenied):
        services.publish_post(post=post, actor=writer.user)


# --- creating and editing ----------------------------------------------------


def test_a_writer_creates_a_draft(client, writer):
    sign_in(client, writer.user)

    client.post(reverse("staff:blog_create"), {
        "title": "My first post", "slug": "", "excerpt": "",
        "content": "Some words about marketing.",
        "featured_image_alt": "", "published_at": "",
        "meta_title": "", "meta_description": "",
    })

    post = BlogPost.objects.get(title="My first post")
    assert post.status == PublishStatus.DRAFT
    assert post.slug == "my-first-post", "a blank slug is derived from the title"


def test_the_author_is_recorded_on_creation(client, writer):
    sign_in(client, writer.user)

    client.post(reverse("staff:blog_create"), {
        "title": "Attributed", "slug": "", "excerpt": "",
        "content": "Words.", "featured_image_alt": "", "published_at": "",
        "meta_title": "", "meta_description": "",
    })

    assert BlogPost.objects.get(title="Attributed").author_id == writer.user.pk


def test_editing_does_not_steal_the_byline(client, writer, super_admin):
    """A colleague fixing a typo should not become the author."""
    post = make_post("Someone else's post", author=writer.user)
    sign_in(client, super_admin)

    client.post(reverse("staff:blog_edit", args=[post.pk]), {
        "title": "Someone else's post", "slug": post.slug, "excerpt": "",
        "content": "Edited words.", "featured_image_alt": "",
        "published_at": "", "meta_title": "", "meta_description": "",
    })

    post.refresh_from_db()
    assert post.author_id == writer.user.pk


def test_duplicate_titles_get_distinct_slugs(super_admin):
    from apps.cms.forms import BlogPostForm

    for _ in range(2):
        form = BlogPostForm(data={"title": "Same title", "slug": "",
                                  "content": "Words.", "excerpt": "",
                                  "featured_image_alt": "", "meta_title": "",
                                  "meta_description": ""})
        assert form.is_valid(), form.errors
        services.save_post(form=form, actor=super_admin, created=True)

    slugs = sorted(BlogPost.objects.values_list("slug", flat=True))
    assert slugs == ["same-title", "same-title-2"]


def test_an_image_without_a_description_is_refused():
    """Invisible to anyone using a screen reader, so the form will not
    accept one."""
    from django.core.exceptions import ValidationError

    post = BlogPost(title="Pictured", slug="pictured", content="Words.",
                    featured_image="blog/x.jpg", featured_image_alt="")

    with pytest.raises(ValidationError) as error:
        post.full_clean(exclude=["author"])

    assert "featured_image_alt" in error.value.message_dict


# --- publishing --------------------------------------------------------------


def test_publishing_puts_a_post_live(client, super_admin):
    post = make_post("Going live", published=False)
    sign_in(client, super_admin)

    client.post(reverse("staff:blog_publish", args=[post.pk]), {"publish": "1"})
    post.refresh_from_db()

    assert post.is_published
    assert client.get("/blog/going-live/").status_code == 200


def test_unpublishing_takes_it_down(client, super_admin):
    post = make_post("Going away")
    sign_in(client, super_admin)

    client.post(reverse("staff:blog_publish", args=[post.pk]), {"publish": "0"})

    assert client.get("/blog/going-away/").status_code == 404


def test_republishing_keeps_the_original_date(super_admin):
    """So fixing a typo does not move the post to the top of the listing."""
    original = timezone.now() - timezone.timedelta(days=30)
    post = make_post("Old post", published_at=original)

    services.unpublish_post(post=post, actor=super_admin)
    services.publish_post(post=post, actor=super_admin)
    post.refresh_from_db()

    assert post.published_at == original


# --- the list screen ---------------------------------------------------------


def test_the_list_shows_drafts_as_well_as_live_posts(client, super_admin):
    make_post("A live one")
    make_post("A draft one", published=False)
    sign_in(client, super_admin)

    body = client.get(reverse("staff:module_blog")).content

    assert b"A live one" in body
    assert b"A draft one" in body


def test_the_list_can_be_filtered_by_status(client, super_admin):
    make_post("A live one")
    make_post("A draft one", published=False)
    sign_in(client, super_admin)

    body = client.get(reverse("staff:module_blog"), {"status": "draft"}).content

    assert b"A draft one" in body
    assert b"A live one" not in body


def test_the_list_can_be_searched(client, super_admin):
    make_post("Findable post")
    make_post("Other post")
    sign_in(client, super_admin)

    body = client.get(reverse("staff:module_blog"), {"q": "Findable"}).content

    assert b"Findable post" in body
    assert b"Other post" not in body


def test_a_scheduled_post_is_marked_as_such(client, super_admin):
    make_post("Later", published_at=timezone.now() + timezone.timedelta(days=2))
    sign_in(client, super_admin)

    assert b"Scheduled" in client.get(reverse("staff:module_blog")).content


# --- categories and tags -----------------------------------------------------


@pytest.mark.parametrize("key", ["blog-categories", "blog-tags"])
def test_the_category_and_tag_screens_render(client, super_admin, key):
    sign_in(client, super_admin)

    assert client.get(reverse("staff:cms_collection", args=[key])).status_code == 200


def test_creating_a_category_derives_its_slug(client, super_admin):
    sign_in(client, super_admin)

    client.post(reverse("staff:cms_collection_create", args=["blog-categories"]), {
        "name": "Paid Media", "slug": "", "description": "", "is_visible": "on",
    })

    assert Category.objects.get(name="Paid Media").slug == "paid-media"


def test_creating_a_tag_derives_its_slug(client, super_admin):
    sign_in(client, super_admin)

    client.post(reverse("staff:cms_collection_create", args=["blog-tags"]), {
        "name": "Core Web Vitals", "slug": "", "is_visible": "on",
    })

    assert Tag.objects.get(name="Core Web Vitals").slug == "core-web-vitals"


def test_deleting_a_category_leaves_its_posts_in_place(super_admin):
    """A post without a category is fine; a post that vanished with its
    category would not be."""
    category = make_category("Temporary")
    post = make_post("Survivor", category=category)

    category.delete()
    post.refresh_from_db()

    assert post.category_id is None
    assert BlogPost.objects.filter(pk=post.pk).exists()


def test_deleting_a_tag_leaves_its_posts_in_place(super_admin):
    tag = make_tag("Temporary")
    post = make_post("Survivor", tags=[tag])

    tag.delete()
    post.refresh_from_db()

    assert BlogPost.objects.filter(pk=post.pk).exists()
    assert post.tags.count() == 0
