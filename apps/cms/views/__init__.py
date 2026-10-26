"""CMS views: the public website, the blog, and the staff screens."""

from apps.cms.views import admin, blog
from apps.cms.views.public import contact_page, home, page_detail, robots_txt

__all__ = ["admin", "blog", "contact_page", "home", "page_detail", "robots_txt"]
