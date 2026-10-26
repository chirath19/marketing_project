from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    # The landing page is now a CMS page — see apps/cms/urls.py. What is
    # left here is the styleguide, which is a development surface.
    path("styleguide/", views.styleguide, name="styleguide"),
]
