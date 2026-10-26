"""The staff screens that manage the blog.

Posts get their own list and form because they have more to them than a
collection row — a status filter, a search, a schedule, and publishing as
a separate right. Categories and tags ride the generic collection views
already built for the rest of the CMS.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.cms import services
from apps.cms.forms import BlogPostForm
from apps.cms.models import BlogPost, Category, PublishStatus
from apps.permissions.guards import require_permission

BLOG_BREADCRUMB = [{"label": "Blog", "href": "/staff/blog/"}]

POSTS_PER_PAGE = 20


def _shell(title: str, subtitle: str = "", **extra) -> dict:
    return {"page_title": title, "page_subtitle": subtitle,
            "nav_key": "blog", **extra}


@require_permission("blog_view")
def post_list(request: HttpRequest) -> HttpResponse:
    """Every post, including drafts — this is the editor's view."""
    posts = BlogPost.objects.all().for_listing()

    status = request.GET.get("status", "")
    if status in PublishStatus.values:
        posts = posts.filter(status=status)

    category = request.GET.get("category", "")
    if category:
        posts = posts.filter(category__slug=category)

    search = (request.GET.get("q") or "").strip()
    if search:
        posts = posts.filter(Q(title__icontains=search)
                             | Q(excerpt__icontains=search))

    paginator = Paginator(posts, POSTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    querystring = "&".join(
        f"{key}={value}" for key, value in
        (("status", status), ("category", category), ("q", search)) if value
    )

    return render(request, "cms/admin/blog_list.html", _shell(
        "Blog", "Posts, drafts and what is scheduled.",
        page_obj=page_obj, posts=page_obj.object_list,
        categories=Category.objects.visible(),
        status=status, category=category, search=search,
        querystring=querystring,
        statuses=PublishStatus.choices,
        columns=[{"label": "Post"}, {"label": "Category"}, {"label": "Status"},
                 {"label": "Published"},
                 {"label": "", "align": "right", "sr_label": "Actions"}],
    ))


@require_permission("blog_create")
@require_http_methods(["GET", "POST"])
def post_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = BlogPostForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                post = services.save_post(form=form, actor=request.user,
                                          created=True)
            except ValidationError as exc:
                for message in exc.messages:
                    form.add_error(None, message)
            else:
                messages.success(request, _("Draft saved."))
                return redirect("staff:blog_edit", pk=post.pk)
    else:
        form = BlogPostForm()

    return render(request, "cms/admin/blog_form.html", _shell(
        "New post", "It is saved as a draft until you publish it.",
        form=form, breadcrumbs=BLOG_BREADCRUMB, creating=True,
    ))


@require_permission("blog_edit")
@require_http_methods(["GET", "POST"])
def post_edit(request: HttpRequest, pk: int) -> HttpResponse:
    post = get_object_or_404(BlogPost, pk=pk)

    if request.method == "POST":
        form = BlogPostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            try:
                services.save_post(form=form, actor=request.user)
            except ValidationError as exc:
                for message in exc.messages:
                    form.add_error(None, message)
            else:
                messages.success(request, _("Post saved."))
                return redirect("staff:blog_edit", pk=post.pk)
    else:
        form = BlogPostForm(instance=post)

    return render(request, "cms/admin/blog_form.html", _shell(
        post.title, f"/blog/{post.slug}/",
        form=form, post=post, breadcrumbs=BLOG_BREADCRUMB,
    ))


@require_permission("blog_publish")
@require_http_methods(["POST"])
def post_publish(request: HttpRequest, pk: int) -> HttpResponse:
    post = get_object_or_404(BlogPost, pk=pk)

    if request.POST.get("publish") == "1":
        services.publish_post(post=post, actor=request.user)
        if post.is_scheduled:
            messages.success(request, _(
                "Scheduled. It appears on the site on %(date)s."
            ) % {"date": post.published_at.strftime("%-d %B %Y")})
        else:
            messages.success(request, _("%(title)s is live.") % {
                "title": post.title})
    else:
        services.unpublish_post(post=post, actor=request.user)
        messages.success(request, _("%(title)s is back to draft.") % {
            "title": post.title})

    return redirect("staff:blog_edit", pk=post.pk)


@require_permission("blog_delete")
@require_http_methods(["POST"])
def post_delete(request: HttpRequest, pk: int) -> HttpResponse:
    post = get_object_or_404(BlogPost, pk=pk)
    services.delete_post(post=post, actor=request.user)
    messages.success(request, _("Post deleted."))
    return redirect("staff:module_blog")
