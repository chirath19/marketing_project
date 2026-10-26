"""Public website routes.

Included last in the root URLconf, because `<slug:slug>/` would otherwise
swallow paths belonging to the dashboard or the API. Blog routes come
before it for the same reason.
"""

from django.contrib.sitemaps.views import sitemap
from django.urls import path

from apps.catalog.views import public as catalog_public
from apps.cms.feeds import BlogFeed
from apps.cms.sitemaps import SITEMAPS
from apps.cms.views import blog, public
from apps.leads.views import guest as guest_quotes
from apps.leads.views import public as leads_public

app_name = "public"

urlpatterns = [
    path("quote/track/<str:token>/", guest_quotes.detail, name="guest_quote"),
    path("", public.home, name="home"),
    path("robots.txt", public.robots_txt, name="robots"),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS},
         name="django.contrib.sitemaps.views.sitemap"),

    path("blog/", blog.blog_index, name="blog"),
    path("blog/feed/", BlogFeed(), name="blog_feed"),
    path("blog/category/<slug:slug>/", blog.blog_category, name="blog_category"),
    path("blog/tag/<slug:slug>/", blog.blog_tag, name="blog_tag"),
    path("blog/<slug:slug>/", blog.blog_detail, name="blog_detail"),

    # The contact page is a CMS page; the form on it is owned by the
    # leads domain, which is where submissions are stored.
    path("contact/", public.contact_page, name="contact"),
    path("contact/enquiry/", leads_public.contact_form, name="contact_form"),
    path("contact/sent/", leads_public.contact_sent, name="contact_sent"),

    # The service catalogue, owned by apps.catalog but part of the public
    # site, so its routes live alongside the rest of it.
    path("services/", catalog_public.services_index, name="services"),
    path("services/category/<slug:slug>/", catalog_public.services_category,
         name="services_category"),
    path("services/<slug:slug>/", catalog_public.service_detail,
         name="service_detail"),

    path("quote/", catalog_public.quote_review, name="quote"),
    path("quote/add/", catalog_public.quote_add, name="quote_add"),
    path("quote/remove/", catalog_public.quote_remove, name="quote_remove"),
    path("quote/clear/", catalog_public.quote_clear, name="quote_clear"),
    path("quote/send/", leads_public.quote_submit, name="quote_submit"),
    path("quote/sent/", leads_public.quote_sent, name="quote_sent"),

    # Last: this would otherwise swallow every path above it.
    path("<slug:slug>/", public.page_detail, name="page"),
]
