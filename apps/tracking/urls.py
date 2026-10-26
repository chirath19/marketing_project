from django.urls import path

from apps.tracking import views

app_name = "tracking"

urlpatterns = [
    path("event/", views.record, name="record_event"),
]
