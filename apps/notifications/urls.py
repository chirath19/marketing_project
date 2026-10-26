from django.urls import path

from apps.notifications import views

app_name = "notifications"
urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("summary/", views.summary, name="summary"),
    path("read/", views.read_all, name="read_all"),
    path("<int:pk>/open/", views.open_notification, name="open"),
]
