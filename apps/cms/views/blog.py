"""The public blog.

Listing, detail, category and tag pages. Published posts only — a draft
is a 404 for everyone, the same rule the rest of the public site follows.
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from apps.cms import selectors
from apps.cms.models import Category, Tag

#: Twelve fits the three-column grid exactly at every breakpoint.
POSTS_PER_PAGE = 12


def _listing(request: HttpRequest, posts, *, title: str, subtitle: str = "",
             eyebrow: str = "", meta_description: str = "",
             active_category: str = "", active_tag: str = "",
             canonical_path: str = "") -> HttpResponse:
    """The shared listing page.

    One template for the index, category and tag views: they differ in
    which posts they show and what the heading says, and nothing else.
    """
    search = request.GET.get("q", "").strip()[:200]
    if search:
        posts = posts.filter(
            Q(title__icontains=search) | Q(excerpt__icontains=search)
            | Q(content__icontains=search)
        )
    search_params = request.GET.copy()
    search_params.pop("page", None)
    paginator = Paginator(posts, POSTS_PER_PAGE)
    page_number = request.GET.get("page") or 1
    try:
        page_obj = paginator.page(page_number)
    except Exception:
        # A page number past the end, or not a number at all. Showing the
        # first page beats a 404 for someone following a stale link.
        page_obj = paginator.page(1)

    return render(request, "public/blog/list.html", {
        "page_title": title,
        "page_subtitle": subtitle,
        "eyebrow": eyebrow,
        "meta_description": meta_description or subtitle,
        "page_obj": page_obj,
        "posts": page_obj.object_list,
        "categories": selectors.visible_categories(),
        "tags": selectors.visible_tags(),
        "active_category": active_category,
        "active_tag": active_tag,
        "canonical_path": canonical_path,
        "search": search,
        "search_querystring": search_params.urlencode(),
    })


def blog_index(request: HttpRequest) -> HttpResponse:
    return _listing(
        request, selectors.published_posts(),
        title="Blog", eyebrow="Writing",
        subtitle="What we are learning, and what is working.",
        canonical_path="/blog/",
    )


def blog_category(request: HttpRequest, slug: str) -> HttpResponse:
    category = get_object_or_404(Category.objects.visible(), slug=slug)

    return _listing(
        request, selectors.posts_in_category(slug),
        title=category.name, eyebrow="Category",
        subtitle=category.description,
        meta_description=category.description or f"Posts about {category.name}.",
        active_category=slug,
        canonical_path=category.get_absolute_url(),
    )


def blog_tag(request: HttpRequest, slug: str) -> HttpResponse:
    tag = get_object_or_404(Tag.objects.visible(), slug=slug)

    return _listing(
        request, selectors.posts_with_tag(slug),
        title=f"#{tag.name}", eyebrow="Tag",
        subtitle=f"Posts tagged {tag.name}.",
        active_tag=slug,
        canonical_path=tag.get_absolute_url(),
    )


def blog_detail(request: HttpRequest, slug: str) -> HttpResponse:
    post = selectors.published_post(slug)
    if post is None:
        raise Http404("No published post at that address.")

    return render(request, "public/blog/detail.html", {
        "post": post,
        "related": selectors.related_posts(post),
        "meta_title": post.resolved_meta_title(),
        "meta_description": post.resolved_meta_description(),
    })
